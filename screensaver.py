#!/usr/bin/env python3
"""The Terminal Screensaver — a sky clock for your terminal.

A big block-font clock over a live sunrise-to-sunset sky gradient, with local
weather, moon phase, and an evergreen treeline that changes with the season,
the weather and the calendar.

Truecolor (24-bit) throughout via \\033[38;2;R;G;Bm escapes — no curses, no
dependencies beyond the Python standard library. Requires a real terminal.
Press any key to exit.

    ./screensaver.py                 live
    ./screensaver.py --location Oslo
    ./screensaver.py christmas       preview any occasion or season
    ./screensaver.py --help

Everything you are likely to want to change is in the CONFIGURATION block just
below. See README.md for the full tour.
"""

import os
import sys
import json
import math
import time
import select
import signal
import termios
import tty
import random
import datetime
import threading
import urllib.parse
import urllib.request

# ═══════════════════════════════════════════════════════════════════════════
#  CONFIGURATION  — edit this block, that is the whole setup
# ═══════════════════════════════════════════════════════════════════════════

# Where to get weather from. Leave empty to let wttr.in guess from your IP.
# Or name a place: "Oslo", "Boulder,CO", "Kyoto", "~Mount Everest",
# "~LHR" (airport), or "48.85,2.35" (coordinates). Overridable at runtime with
#   ./screensaver.py --location "Lisbon"
LOCATION = ""

# Temperature units: "F" or "C". Also --units C on the command line.
UNITS = "F"

# Coordinates for the offline sun almanac (sunrise/sunset without a network).
# None means "learn them from the weather reply", which works as soon as the
# first fetch succeeds. Set them yourself to have correct sun times even with
# no internet at all — e.g. LATITUDE, LONGITUDE = 59.91, 10.75 for Oslo.
LATITUDE = None
LONGITUDE = None

# Optional birthday greeting: (month, day), or None to turn it off.
# BIRTHDAY_NAME may be left empty for a plain "Happy Birthday!".
BIRTHDAY = (6, 15)
BIRTHDAY_NAME = ""

# ═══════════════════════════════════════════════════════════════════════════

_WX_TTL = 1800                  # a cached reading stays usable this long (30 min)
_RETRIES = (5, 15, 45)          # backoff between attempts within one poll cycle
_FALLBACK_SUN = (390, 1110)     # 06:30 / 18:30, used only when the location is
                                # still completely unknown (no fetch, no coords)

_wx: dict = {}
_wx_lock = threading.Lock()

# Preview mode (see main()): _OFFSET shifts the whole scene's idea of "now",
# _FAKE_COND forces a weather condition. Both zero/None in normal use, so the
# live screensaver is unaffected.
_OFFSET = 0.0
_FAKE_COND = None


def _clock():
    """Seconds since the epoch as the scene sees it (real time + preview shift)."""
    return time.time() + _OFFSET


# ═══════════════════════════════════════════════════════════════════════════
#  weather fetch
# ═══════════════════════════════════════════════════════════════════════════
def weather_url():
    """wttr.in endpoint for the configured location (empty = guess from IP)."""
    return f"https://wttr.in/{urllib.parse.quote(LOCATION)}?format=j1"


def _place_name(d):
    """A short, display-ready name for whatever wttr.in decided we asked about."""
    try:
        area = d["nearest_area"][0]
        city = area["areaName"][0]["value"]
        region = (area.get("region") or [{}])[0].get("value", "")
        country = (area.get("country") or [{}])[0].get("value", "")
        second = region or country
        # "Kyoto, Japan" is nice; "Singapore, Singapore" is not
        return f"{city}, {second}" if second and second != city else city
    except Exception:
        return LOCATION or "LOCAL WEATHER"


def _fetch_once():
    req = urllib.request.Request(weather_url(), headers={"User-Agent": "curl/7.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        d = json.loads(r.read())
    cur   = d["current_condition"][0]
    today = d["weather"][0]
    astro = today["astronomy"][0]
    u = "C" if UNITS.upper().startswith("C") else "F"
    out = {
        "temp":    cur[f"temp_{u}"],
        "feels":   cur[f"FeelsLike{u}"],
        "desc":    cur["weatherDesc"][0]["value"].strip(),
        "humid":   cur["humidity"],
        "hi":      today[f"maxtemp{u}"],
        "lo":      today[f"mintemp{u}"],
        "unit":    u,
        "place":   _place_name(d).upper(),
        "code":    int(cur.get("weatherCode", 113)),
        "sunrise": astro["sunrise"],
        "sunset":  astro["sunset"],
        "ok":      True,
        "stale":   False,
        "ts":      time.time(),
    }
    # Learn coordinates for the offline almanac, unless they were configured.
    if LATITUDE is None or LONGITUDE is None:
        try:
            area = d["nearest_area"][0]
            out["lat"] = float(area["latitude"])
            out["lon"] = float(area["longitude"])
        except Exception:
            pass
    return out


def _fetch_wx():
    """Poll wttr.in forever, preferring real data as hard as is reasonable.

    wttr.in is a free community service with no SLA — it rate-limits, and it
    goes down now and then. So each 5-minute cycle gets up to four attempts
    with 5s/15s/45s backoff, and a cycle that still fails keeps serving the
    last good reading (marked stale) instead of blanking the panel. Only after
    _WX_TTL with nothing fresh does the display admit defeat; sun times fall
    back to the local almanac in sun_times(), never to a guess.
    """
    while True:
        for delay in _RETRIES + (None,):
            try:
                fresh = _fetch_once()
                with _wx_lock:
                    _wx.update(fresh)
                _learn_tz_shift()
                break
            except Exception:
                if delay is None:                      # all attempts spent
                    with _wx_lock:
                        age = time.time() - _wx.get("ts", 0)
                        _wx["stale"] = True
                        _wx["ok"] = bool(_wx.get("ts")) and age < _WX_TTL
                else:
                    time.sleep(delay)
        time.sleep(300)


# ═══════════════════════════════════════════════════════════════════════════
#  color helpers
# ═══════════════════════════════════════════════════════════════════════════
def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    """Interpolate two RGB tuples. t clamped to [0,1]."""
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return (int(round(lerp(c1[0], c2[0], t))),
            int(round(lerp(c1[1], c2[1], t))),
            int(round(lerp(c1[2], c2[2], t))))


def scale(c, f):
    return (max(0, min(255, int(c[0] * f))),
            max(0, min(255, int(c[1] * f))),
            max(0, min(255, int(c[2] * f))))


def lum(c):
    """Perceived luminance 0..255."""
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def contrast_fg(fg, bg, min_delta=115):
    """Keep fg if it reads clearly against bg; otherwise snap it to a legible
    near-white or near-black so text never disappears into the sky."""
    if abs(lum(fg) - lum(bg)) >= min_delta:
        return fg
    return (244, 247, 255) if lum(bg) < 128 else (14, 18, 30)


# ═══════════════════════════════════════════════════════════════════════════
#  moon phase
# ═══════════════════════════════════════════════════════════════════════════
def moon_phase():
    jd  = _clock() / 86400.0 + 2440587.5
    age = (jd - 2451550.1) % 29.53058867
    illum = int((1 - math.cos(2 * math.pi * age / 29.53058867)) / 2 * 100)
    if   age <  1.85: return "New Moon",        illum, "○"
    elif age <  7.38: return "Waxing Crescent", illum, "◐"
    elif age <  9.22: return "First Quarter",   illum, "◐"
    elif age < 14.77: return "Waxing Gibbous",  illum, "◐"
    elif age < 16.61: return "Full Moon",       illum, "●"
    elif age < 22.15: return "Waning Gibbous",  illum, "◑"
    elif age < 23.99: return "Last Quarter",    illum, "◑"
    else:             return "Waning Crescent", illum, "◑"


# ═══════════════════════════════════════════════════════════════════════════
#  weather classification
# ═══════════════════════════════════════════════════════════════════════════
_STORM = {200, 386, 389, 392, 395}
_HRAIN = {305, 308, 356, 359}
_RAIN  = {263, 266, 293, 296, 299, 302, 353,
          176, 182, 185, 281, 284, 311, 314, 317, 320, 374, 377}
_SNOW  = {179, 227, 230, 323, 326, 329, 332, 335, 338, 362, 365, 368, 371}
_FOG   = {143, 248, 260}


def classify(code):
    if code in _STORM:     return "storm"
    if code in _HRAIN:     return "hrain"
    if code in _RAIN:      return "rain"
    if code in _SNOW:      return "snow"
    if code in _FOG:       return "fog"
    if code in {119, 122}: return "cloudy"
    if code == 116:        return "pcloudy"
    return "clear"


# ═══════════════════════════════════════════════════════════════════════════
#  time-of-day sky palette  (continuous, anchored to real sun times)
# ═══════════════════════════════════════════════════════════════════════════
def _hhmm(s):
    parts = s.strip().split()
    h, m  = map(int, parts[0].split(':'))
    ampm  = parts[1].upper()
    if   ampm == 'PM' and h != 12: h += 12
    elif ampm == 'AM' and h == 12: h = 0
    return h * 60 + m


def _coords():
    """(lat, lon) from CONFIGURATION, else whatever the weather reply told us."""
    if LATITUDE is not None and LONGITUDE is not None:
        return LATITUDE, LONGITUDE
    with _wx_lock:
        lat, lon = _wx.get("lat"), _wx.get("lon")
    return (lat, lon) if lat is not None and lon is not None else (None, None)


def _tz_shift():
    """Minutes to add to almanac times so they land in the *location's* clock.

    sun_times() renders into this computer's timezone, which is exactly right
    when the configured location is where you are — the normal case, and the
    assumption when nothing better is known. Once a weather reply has been
    seen we can do better: compare its (location-local) sunrise against our
    own computation and keep the difference, so even a remote location stays
    correct after the network goes away. Rounded to a quarter hour, which
    covers every real timezone and absorbs the almanac's minute or two of
    error.
    """
    with _wx_lock:
        return _wx.get("tz_shift", 0)


def _learn_tz_shift():
    """Called after a successful fetch; see _tz_shift()."""
    with _wx_lock:
        sr = _wx.get("sunrise")
        _wx["tz_shift"] = 0                  # measure against an unshifted run
    if not sr:
        return
    try:
        actual = _hhmm(sr)
    except Exception:
        return
    guess = sun_times()
    if not guess:
        return
    delta = (actual - guess[0] + 720) % 1440 - 720
    with _wx_lock:
        _wx["tz_shift"] = int(round(delta / 15.0)) * 15


def sun_times(when=None):
    """Local sunrise/sunset (minutes past midnight) for the current location.

    Standard NOAA solar-position math — accurate to a minute or two, needs no
    network, and handles DST via the platform's own UTC offset. Used when
    wttr.in has never answered; a *stale* wttr.in reading is preferred over
    this, since day-old sun times only drift a minute or two anyway.

    Returns None if the location is still unknown, or above the polar circles
    in the weeks when the sun does not rise or set at all.
    """
    lat, lon = _coords()
    if lat is None:
        return None
    when = when or datetime.date.fromtimestamp(_clock())
    # days since J2000.0 — which is 2000-01-01 *12:00* UT, so count from noon,
    # plus the 0.0008 leap-second fudge NOAA uses
    jd_noon = when.toordinal() + 1721425.0     # JD at 12:00 UT on `when`
    n = jd_noon - 2451545.0 + 0.0008
    J_star = n - lon / 360.0                   # mean solar time at this meridian
    M = math.radians((357.5291 + 0.98560028 * J_star) % 360.0)
    C = (1.9148 * math.sin(M) + 0.0200 * math.sin(2 * M)
         + 0.0003 * math.sin(3 * M))
    lam = math.radians((math.degrees(M) + C + 180.0 + 102.9372) % 360.0)
    J_transit = (2451545.0 + J_star + 0.0053 * math.sin(M)
                 - 0.0069 * math.sin(2 * lam))
    decl = math.asin(math.sin(lam) * math.sin(math.radians(23.44)))
    phi = math.radians(lat)
    # -0.833° = refraction + the sun's own radius, i.e. first/last limb visible
    cos_w = ((math.sin(math.radians(-0.833)) - math.sin(phi) * math.sin(decl))
             / (math.cos(phi) * math.cos(decl)))
    if not -1.0 <= cos_w <= 1.0:
        return None                            # midnight sun / polar night
    w = math.degrees(math.acos(cos_w))
    shift = _tz_shift()
    out = []
    for jday in (J_transit - w / 360.0, J_transit + w / 360.0):
        epoch = (jday - 2440587.5) * 86400.0   # JD -> unix time
        lt = time.localtime(epoch)             # -> local clock, DST included
        out.append((lt.tm_hour * 60 + lt.tm_min + shift) % 1440)
    return tuple(out)                          # (sunrise, sunset)


# Each anchor: sky-top, horizon, text, accent, star-density
#   sky-top  : color at the top of the frame
#   horizon  : color just above the ground line
#   text     : clock / label color (kept legible against the sky)
#   accent   : warm/decorative highlight
#   star     : 0..1 star visibility
_NIGHT = dict(top=(6, 8, 26),   hor=(14, 16, 40),  txt=(206, 216, 255),
              acc=(126, 156, 224), star=1.0)


def _anchors(R, S):
    return [
        (0,        _NIGHT),
        (R - 65,   dict(top=(18, 16, 46), hor=(64, 42, 74),   txt=(210, 210, 240), acc=(158, 122, 186), star=0.70)),
        (R - 32,   dict(top=(42, 36, 84), hor=(158, 84, 84),  txt=(240, 226, 226), acc=(232, 142, 112), star=0.32)),
        (R,        dict(top=(74, 74, 134), hor=(255, 150, 70), txt=(255, 240, 220), acc=(255, 182, 92),  star=0.08)),
        (R + 45,   dict(top=(112, 152, 208), hor=(255, 206, 152), txt=(38, 50, 82),  acc=(250, 200, 120), star=0.0)),
        (R + 95,   dict(top=(92, 152, 216), hor=(182, 208, 232), txt=(26, 40, 72),  acc=(255, 214, 118), star=0.0)),
        (S - 95,   dict(top=(104, 148, 206), hor=(226, 200, 168), txt=(30, 44, 76), acc=(252, 190, 110), star=0.0)),
        (S - 42,   dict(top=(120, 120, 190), hor=(248, 188, 118), txt=(44, 40, 78), acc=(252, 172, 92),  star=0.0)),
        (S - 12,   dict(top=(96, 78, 156),  hor=(255, 150, 82),  txt=(255, 236, 216), acc=(255, 150, 80), star=0.04)),
        (S,        dict(top=(62, 46, 112),  hor=(255, 108, 70),  txt=(255, 226, 206), acc=(255, 120, 72), star=0.14)),
        (S + 28,   dict(top=(32, 28, 74),   hor=(154, 72, 82),   txt=(236, 216, 222), acc=(212, 112, 112), star=0.42)),
        (S + 72,   dict(top=(15, 15, 46),   hor=(52, 38, 72),    txt=(216, 216, 240), acc=(132, 112, 172), star=0.72)),
        (S + 120,  _NIGHT),
        (1440,     _NIGHT),
    ]


_PAL_FIELDS = ("top", "hor", "txt", "acc")


def sky_palette(now_min, R, S):
    tl = _anchors(R, S)
    a, b, t = tl[0][1], tl[0][1], 0.0
    for i in range(len(tl) - 1):
        t0, p0 = tl[i]
        t1, p1 = tl[i + 1]
        if t0 <= now_min < t1:
            a, b = p0, p1
            t = (now_min - t0) / (t1 - t0) if t1 > t0 else 0.0
            break
    pal = {f: mix(a[f], b[f], t) for f in _PAL_FIELDS}
    pal["star"] = lerp(a["star"], b["star"], t)
    return pal


def apply_condition(pal, cond):
    """Tint the sky for overcast / stormy / foggy conditions."""
    if cond == "storm":
        pal = dict(pal)
        pal["top"] = scale(mix(pal["top"], (58, 66, 66), 0.7), 0.7)
        pal["hor"] = scale(mix(pal["hor"], (72, 80, 74), 0.7), 0.8)
    elif cond in ("hrain", "rain"):
        pal = dict(pal)
        pal["top"] = mix(pal["top"], (90, 98, 112), 0.5)
        pal["hor"] = mix(pal["hor"], (120, 128, 140), 0.45)
    elif cond in ("cloudy",):
        pal = dict(pal)
        pal["top"] = mix(pal["top"], (120, 126, 138), 0.45)
        pal["hor"] = mix(pal["hor"], (150, 156, 166), 0.4)
    elif cond == "pcloudy":
        pal = dict(pal)
        pal["top"] = mix(pal["top"], (120, 126, 138), 0.2)
        pal["hor"] = mix(pal["hor"], (150, 156, 166), 0.18)
    elif cond == "fog":
        pal = dict(pal)
        pal["top"] = mix(pal["top"], (150, 152, 158), 0.6)
        pal["hor"] = mix(pal["hor"], (170, 172, 178), 0.6)
    elif cond == "snow":
        pal = dict(pal)
        pal["top"] = mix(pal["top"], (140, 150, 172), 0.45)
        pal["hor"] = mix(pal["hor"], (200, 208, 224), 0.4)
    return pal


def apply_occasion(pal, occ):
    """Decorative sky wash for occasions that ask for one, over the weather
    tint. Deliberately gentle — the sky should still read as the right time of
    day, and `txt` is left alone so the clock keeps its own contrast pass."""
    star = pal.get("star", 0.0)      # 0 = broad daylight, 1 = full dark
    if occ.get("warm"):
        # Christmas: ember glow behind the lit trees. Strongest after dark,
        # when you'd actually be looking at it — by day it's just a faint haze.
        f = 0.45 + 0.55 * star
        pal = dict(pal)
        pal["top"] = mix(pal["top"], (96, 52, 66), 0.22 * f)
        pal["hor"] = mix(pal["hor"], (216, 130, 84), 0.30 * f)
        pal["acc"] = mix(pal["acc"], (255, 178, 118), 0.40 * f)
    elif occ.get("pastel"):
        # Easter: soft, washed-out spring sky. Fades out at night — pastels
        # only read as pastels in daylight; lightening a night sky just
        # muddies it and would wash out the stars.
        f = max(0.0, 1.0 - star)     # fully off once the sky is truly dark
        pal = dict(pal)
        pal["top"] = mix(pal["top"], (196, 206, 242), 0.26 * f)
        pal["hor"] = mix(pal["hor"], (250, 220, 232), 0.32 * f)
        pal["acc"] = mix(pal["acc"], (238, 184, 222), 0.35 * f)
    return pal


# ═══════════════════════════════════════════════════════════════════════════
#  season + holiday occasions
# ═══════════════════════════════════════════════════════════════════════════
def _easter(year):
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime.date(year, month, day)


def _nth_weekday(year, month, weekday, n):
    d = datetime.date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    return d + datetime.timedelta(days=offset + 7 * (n - 1))


def get_season(month):
    if month in (12, 1, 2):  return "winter"
    if month in (3, 4, 5):   return "spring"
    if month in (6, 7, 8):   return "summer"
    return "fall"


def get_occasion(dt):
    """Return an occasion dict of scene flags + greeting for the date, or {}."""
    y, m, d = dt.year, dt.month, dt.day
    today = datetime.date(y, m, d)

    def within(target, days):
        return abs((today - target).days) <= days

    # Birthday (optional — set BIRTHDAY = None to disable)
    if BIRTHDAY and (m, d) == tuple(BIRTHDAY):
        greet = f"Happy Birthday, {BIRTHDAY_NAME}!" if BIRTHDAY_NAME \
                else "Happy Birthday!"
        return dict(name="birthday", greet=greet, confetti=True)
    # New Year
    if (m == 12 and d == 31) or (m == 1 and d <= 2):
        return dict(name="newyear", greet=f"Happy New Year {y if m==1 else y+1}",
                    confetti=True)
    # Christmas window
    if m == 12 and 18 <= d <= 30:
        return dict(name="christmas", greet="Merry Christmas",
                    lights=True, warm=True)
    # Halloween
    if m == 10 and 25 <= d <= 31:
        return dict(name="halloween", greet="Happy Halloween",
                    pumpkins=True, bats=True)
    # Thanksgiving (4th Thursday of Nov)
    if m == 11 and within(_nth_weekday(y, 11, 3, 4), 3):
        return dict(name="thanksgiving", greet="Happy Thanksgiving",
                    heavy_leaves=True)
    # Independence Day
    if m == 7 and 3 <= d <= 5:
        return dict(name="july4", greet="Happy 4th of July",
                    fireworks=True, rwb=True)
    # Easter
    if within(_easter(y), 3):
        return dict(name="easter", greet="Happy Easter",
                    flowers=True, pastel=True)
    # Add your own here — anything local, or a name day, or an anniversary.
    # Keys understood by the scene: greet, lights, pumpkins, bats, confetti,
    # fireworks, flowers, heavy_leaves, warm, pastel. First match wins, so put
    # narrow windows above broad ones. For example:
    #   if m == 5 and 1 <= d <= 5:
    #       return dict(name="spring_fair", greet="Spring Fair", flowers=True)
    return {}


# ═══════════════════════════════════════════════════════════════════════════
#  screen buffer  (truecolor cell diff renderer)
# ═══════════════════════════════════════════════════════════════════════════
_SENTINEL = ("\0", None, None)


class Screen:
    def __init__(self):
        self.w = self.h = 0
        self.front = []
        self.back = []
        self._resize()

    def _resize(self):
        sz = os.get_terminal_size()
        self.w, self.h = sz.columns, sz.lines
        self.front = [[list(_SENTINEL) for _ in range(self.w)] for _ in range(self.h)]
        self.back  = [[[" ", (255, 255, 255), (0, 0, 0)] for _ in range(self.w)]
                      for _ in range(self.h)]
        sys.stdout.write("\033[2J")

    def fill_bg(self, bg_rows, txt):
        """Reset the back buffer to the sky background for this frame."""
        w = self.w
        for y in range(self.h):
            bg = bg_rows[y]
            row = self.back[y]
            for x in range(w):
                c = row[x]
                c[0] = " "
                c[1] = txt
                c[2] = bg

    def put(self, x, y, ch, fg, bg=None):
        if 0 <= y < self.h and 0 <= x < self.w:
            cell = self.back[y][x]
            cell[0] = ch
            cell[1] = fg
            if bg is not None:
                cell[2] = bg

    def text(self, x, y, s, fg, bg=None):
        for i, ch in enumerate(s):
            self.put(x + i, y, ch, fg, bg)

    def bg_at(self, x, y):
        if 0 <= y < self.h and 0 <= x < self.w:
            return self.back[y][x][2]
        return (0, 0, 0)

    def text_a(self, x, y, s, fg):
        """Draw text with per-cell contrast against the sky behind it."""
        for i, ch in enumerate(s):
            if ch == " ":
                continue
            cx = x + i
            if 0 <= cx < self.w and 0 <= y < self.h:
                self.put(cx, y, ch, contrast_fg(fg, self.back[y][cx][2]))

    def render(self):
        out = []
        last_fg = last_bg = None
        pending_pos = None
        cur_row = -1
        for y in range(self.h):
            back_row = self.back[y]
            front_row = self.front[y]
            x = 0
            while x < self.w:
                if y == self.h - 1 and x == self.w - 1:
                    break  # never touch the very last cell (scroll guard)
                nc = back_row[x]
                oc = front_row[x]
                if nc[0] == oc[0] and nc[1] == oc[1] and nc[2] == oc[2]:
                    x += 1
                    continue
                if cur_row != y or pending_pos != x:
                    out.append(f"\033[{y + 1};{x + 1}H")
                fg, bg = nc[1], nc[2]
                if fg != last_fg or bg != last_bg:
                    out.append(f"\033[38;2;{fg[0]};{fg[1]};{fg[2]};"
                               f"48;2;{bg[0]};{bg[1]};{bg[2]}m")
                    last_fg, last_bg = fg, bg
                out.append(nc[0])
                oc[0], oc[1], oc[2] = nc[0], nc[1], nc[2]
                cur_row, pending_pos = y, x + 1
                x += 1
        if out:
            out.append("\033[0m")
            sys.stdout.write("".join(out))
            sys.stdout.flush()


# ═══════════════════════════════════════════════════════════════════════════
#  sky background (cached vertical gradient + twinkling stars)
# ═══════════════════════════════════════════════════════════════════════════
class Sky:
    def __init__(self):
        self.stars = []           # (x, y, phase, base)
        self.seed_w = self.seed_h = 0

    def _seed_stars(self, w, h, horizon):
        self.stars = []
        n = max(20, (w * horizon) // 45)
        for _ in range(n):
            self.stars.append((random.randint(0, w - 1),
                               random.randint(0, max(0, horizon - 1)),
                               random.uniform(0, 2 * math.pi),
                               random.uniform(0.45, 1.0)))
        self.seed_w, self.seed_h = w, h

    def bg_rows(self, w, h, horizon, pal, ground_col):
        top, hor = pal["top"], pal["hor"]
        rows = []
        span = max(1, horizon)
        for y in range(h):
            if y < horizon:
                t = y / span
                # ease toward horizon so the warm band hugs the skyline
                t = t * t
                rows.append(mix(top, hor, t))
            else:
                d = (y - horizon) / max(1, h - horizon)
                rows.append(mix(ground_col, scale(ground_col, 0.55), d))
        return rows

    def draw_stars(self, scr, horizon, pal, t):
        if pal["star"] <= 0.02:
            return
        if self.seed_w != scr.w or self.seed_h != scr.h:
            self._seed_stars(scr.w, scr.h, horizon)
        vis = pal["star"]
        for (x, y, ph, base) in self.stars:
            if y >= horizon:
                continue
            tw = 0.6 + 0.4 * math.sin(t * 1.6 + ph)
            b = base * vis * tw
            if b < 0.18:
                continue
            col = mix(scr.back[y][x][2], (235, 240, 255), min(1.0, b))
            ch = "·" if b < 0.5 else ("✦" if base > 0.9 and b > 0.8 else "•")
            scr.put(x, y, ch, col)


# ═══════════════════════════════════════════════════════════════════════════
#  particles  (weather + seasonal ambient)
# ═══════════════════════════════════════════════════════════════════════════
class Particle:
    __slots__ = ("x", "y", "vx", "vy", "ch", "col", "spec")

    def __init__(self, w, h, spec, seeded=True):
        self.spec = spec
        self.respawn(w, h, seeded)

    def respawn(self, w, h, seeded=False):
        s = self.spec
        self.x = random.uniform(0, w)
        self.y = random.uniform(0, h) if seeded else random.uniform(-2, 0)
        self.vx = random.uniform(*s["vx"])
        self.vy = random.uniform(*s["vy"])
        self.ch = random.choice(s["chars"])
        self.col = random.choice(s["cols"])

    def update(self, w, h):
        self.x += self.vx
        self.y += self.vy
        if self.spec.get("sway"):
            self.x += math.sin(self.y * 0.5) * 0.3
        if self.y >= h or self.x < -1 or self.x >= w + 1:
            self.respawn(w, h)


def particle_spec(cond, season, occ, pal):
    """Choose the ambient particle field for the current conditions."""
    if cond == "storm":
        return dict(n=90, chars="||", cols=[(150, 170, 195), (120, 145, 180)],
                    vx=(-0.05, 0.05), vy=(1.2, 2.0))
    if cond == "hrain":
        return dict(n=80, chars="||", cols=[(120, 148, 190), (100, 130, 178)],
                    vx=(-0.04, 0.04), vy=(1.0, 1.7))
    if cond == "rain":
        return dict(n=60, chars="|.", cols=[(130, 158, 205), (110, 140, 195)],
                    vx=(-0.06, 0.06), vy=(0.7, 1.2))
    if cond == "snow":
        return dict(n=70, chars="*+·❄", cols=[(232, 238, 250), (208, 220, 240)],
                    vx=(-0.2, 0.2), vy=(0.15, 0.4), sway=True)
    if cond == "fog":
        return dict(n=70, chars="·:", cols=[(172, 176, 184), (150, 154, 162)],
                    vx=(-0.15, 0.15), vy=(0.05, 0.15))
    if season == "fall" and cond in ("clear", "pcloudy", "cloudy"):
        n = 55 if occ.get("heavy_leaves") else 30
        return dict(n=n, chars="❦✽,~", cols=[(214, 118, 52), (196, 84, 40),
                    (222, 168, 66), (150, 90, 40)], vx=(-0.35, 0.35),
                    vy=(0.2, 0.5), sway=True)
    if cond in ("cloudy", "pcloudy"):
        return dict(n=20, chars="·", cols=[pal["txt"]], vx=(-0.1, 0.1), vy=(0.05, 0.2))
    # clear day → nothing falling (stars carry the sky); clear night handled by Sky
    return dict(n=0, chars="·", cols=[pal["txt"]], vx=(-0.05, 0.05), vy=(0.05, 0.2))


# ═══════════════════════════════════════════════════════════════════════════
#  holiday effects  (fireworks, confetti, bats)
# ═══════════════════════════════════════════════════════════════════════════
class Effect:
    """A transient spark with a lifetime; dies off-screen or when life runs out."""
    __slots__ = ("x", "y", "vx", "vy", "ch", "col", "life", "grav")

    def __init__(self, x, y, vx, vy, ch, col, life, grav=0.0):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.ch, self.col, self.life, self.grav = ch, col, life, grav

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += self.grav
        self.life -= 1
        return self.life > 0


_RWB = [(230, 70, 70), (245, 245, 250), (80, 120, 235)]
_CONFETTI = [(240, 90, 110), (250, 200, 90), (120, 210, 130),
             (110, 170, 240), (210, 130, 240), (250, 250, 250)]


def spawn_firework(w, horizon):
    cx = random.uniform(w * 0.15, w * 0.85)
    cy = random.uniform(1, max(2, horizon * 0.5))
    col = random.choice(_RWB + [(250, 210, 90), (120, 230, 180)])
    sparks = []
    for _ in range(random.randint(18, 30)):
        ang = random.uniform(0, 2 * math.pi)
        spd = random.uniform(0.3, 1.1)
        sparks.append(Effect(cx, cy, math.cos(ang) * spd,
                             math.sin(ang) * spd * 0.6, random.choice("*+·✦"),
                             col, random.randint(10, 20), grav=0.03))
    return sparks


# ═══════════════════════════════════════════════════════════════════════════
#  nature scene  (seasonal trees, grass, flora, holiday overlays)
# ═══════════════════════════════════════════════════════════════════════════
# Evergreen conifers — irregular, lopsided, billowy crowns with
# ragged edges (▒) and dense interiors (▓), foliage nearly to the ground, and
# the characteristic short multi-trunk. Three hand-drawn shapes for variety.
_CONIFERS = (
    (   # 0 — large, broad, slightly right-leaning
        "     ▒▓▓▒     ",
        "   ▒▓▓▓▓▓▓▒   ",
        "  ▓▓▓▓▓▓▓▓▓▒  ",
        " ▒▓▓▓▓▓▓▓▓▓▓▓ ",
        " ▓▓▓▓▓▓▓▓▓▓▓▓▒",
        "▒▓▓▓▓▓▓▓▓▓▓▓▓ ",
        " ▓▓▓▓▓▓▓▓▓▓▓▒ ",
        "  ▒▓▓█▓▐▓█▓▓  ",
        "     █ ▐ █    ",
    ),
    (   # 1 — medium, lopsided
        "    ▒▓▓▒   ",
        "   ▓▓▓▓▓▒  ",
        "  ▓▓▓▓▓▓▓▓ ",
        " ▒▓▓▓▓▓▓▓▓▒",
        "  ▓▓▓▓▓▓▓▓ ",
        "   ▒▓█▓█▓▒ ",
        "    █ ▐█   ",
    ),
    (   # 2 — small sapling
        "   ▒▓▒ ",
        "  ▓▓▓▓▒",
        " ▒▓▓▓▓▓",
        "  ▒▓█▓ ",
        "    █  ",
    ),
)
_TRUNK = (128, 84, 62)          # reddish-brown bark


def tree_shift(h):
    """Size-class step-down for short windows.

    A 9-row tree is a third of the frame in a ~26-row window, which both
    crowds the picture and leaves the overlay nowhere to sit. Stepping each
    tree down a size class keeps the treeline proportional. Returns 0 on a
    normal-height terminal, where the full-size sprites are used.
    """
    return 2 if h < 24 else (1 if h < 26 else 0)


def tallest_tree(h):
    """Rows of foliage in the biggest tree actually drawn at height `h`."""
    return len(_CONIFERS[min(len(_CONIFERS) - 1, tree_shift(h))])

_SEASON_GROUND = {
    "spring": (58, 96, 48), "summer": (108, 104, 46),
    "fall":   (96, 74, 40), "winter": (78, 80, 86),
}
_SEASON_GRASS = {
    "spring": (86, 158, 70), "summer": (150, 150, 66),
    "fall":   (140, 108, 56), "winter": (110, 116, 120),
}


def _blit(scr, sprite, x0, y0, colfn, lit=None):
    """Draw a sprite; colfn(ch, i, j) -> (rgb, is_foliage) or None (skip).
    Foliage cells are appended to `lit` (for holiday-light placement)."""
    for i, line in enumerate(sprite):
        for j, ch in enumerate(line):
            if ch == " ":
                continue
            res = colfn(ch, i, j)
            if res is None:
                continue
            col, is_foliage = res
            scr.put(x0 + j, y0 + i, ch, col)
            if is_foliage and lit is not None:
                lit.append((x0 + j, y0 + i))


def draw_tree(scr, sprite, x0, y0, snowy, season, depth, lit):
    """A single tree. Top rows are sunlit (lighter), interior/lower rows fall
    into shadow — a vertical shade that gives the crown real volume. `depth`
    (0..1) hazes background trees back into the treeline."""
    n = len(sprite)
    top = (86, 120, 96)          # sunlit blue-green
    bot = (26, 52, 42)           # shadowed interior
    if season == "winter":       # winter foliage goes bronze
        top = mix(top, (144, 122, 82), 0.28)
        bot = mix(bot, (110, 96, 66), 0.28)
    haze = (128, 146, 158)

    def colfn(ch, i, j):
        if ch in "█▐▌":
            return _TRUNK, False
        f = i / (n - 2) if n > 2 else 0.0          # trunk row excluded from shade
        c = mix(top, bot, min(1.0, f))
        m = (((i * 13 + j * 7) % 5) - 2) * 7        # mottle for density
        c = (max(0, min(255, c[0] + m)),
             max(0, min(255, c[1] + m)),
             max(0, min(255, c[2] + m)))
        if ch == "▒":                               # ragged edge → sparser/darker
            c = mix(c, bot, 0.4)
        if snowy and i < 2:
            c = mix(c, (232, 238, 248), 0.5)
        if depth > 0:
            c = mix(c, haze, depth * 0.55)
        return c, True
    _blit(scr, sprite, x0, y0, colfn, lit)


def _treeline(w):
    """Positions for a scattered treeline: (x, sprite_index, depth), drawn
    back-to-front. Skips trees that would fall off a narrow screen."""
    big, med, sml = 0, 1, 2
    trees = [
        (1,          big, 0.0),
        (int(w * 0.16), sml, 0.35),
        (int(w * 0.24), med, 0.15),
        (w - 14,     big, 0.0),
        (w - 22,     med, 0.2),
        (w - 30,     sml, 0.35),
    ]
    if w > 96:
        trees += [(int(w * 0.44), sml, 0.5), (int(w * 0.54), med, 0.4)]
    ww = [len(_CONIFERS[si][0]) for _, si, _ in trees]
    return [tr for tr, wd in zip(trees, ww) if 0 <= tr[0] <= w - 1]


def draw_scene(scr, pal, season, occ, snowy, t):
    w, h = scr.w, scr.h
    horizon = h - 3
    grass_row = h - 3
    ground = mix(_SEASON_GROUND[season], (255, 255, 255), 0.15) if snowy else _SEASON_GROUND[season]

    grass = _SEASON_GRASS[season]
    if snowy:
        grass = mix(grass, (235, 240, 248), 0.6)

    # grass strip with flora
    flowers = occ.get("flowers") or season == "spring"
    # Soft breeze: each blade's lean drifts as a slow sine over time, with a
    # phase offset per column so the sway ripples across the field rather than
    # every blade snapping in unison (or jittering frame-to-frame).
    for x in range(1, w - 1):
        r = (x * 2654435761) & 0xFFFFFFFF
        pick = r % 12
        if flowers and pick == 0:
            scr.put(x, grass_row, "✿", (120, 130, 235))          # blue flower
        elif flowers and pick == 1:
            scr.put(x, grass_row, "❀", (232, 96, 96))            # red flower
        elif pick < 5:
            sway = math.sin(t * 0.6 + x * 0.22)                  # ~10s period
            blade = "/" if sway > 0.4 else ("\\" if sway < -0.4 else "|")
            scr.put(x, grass_row, blade, grass)
        else:
            scr.put(x, grass_row, "‸" if pick == 5 else "ⵦ", mix(grass, ground, 0.3))

    lit_positions = []

    # ── treeline (drawn back-to-front for depth) ──────────────────────────
    shift = tree_shift(h)
    for x, si, depth in sorted(_treeline(w), key=lambda tr: -tr[2]):
        sp = _CONIFERS[min(len(_CONIFERS) - 1, si + shift)]
        draw_tree(scr, sp, x, h - 2 - len(sp), snowy, season, depth,
                  lit_positions)

    # Christmas lights sprinkled on foliage
    if occ.get("lights") and lit_positions:
        lights = [(240, 80, 80), (250, 220, 90), (110, 200, 120), (110, 160, 245)]
        step = max(3, len(lit_positions) // 14)
        for k, (col, row) in enumerate(lit_positions[::step]):
            phase = (t * 2 + k) % len(lights)
            scr.put(col, row, "●", lights[int(phase)])

    # Jack-o-lanterns at the grass line for Halloween
    if occ.get("pumpkins"):
        for px in (int(w * 0.4), int(w * 0.6)):
            scr.put(px, grass_row, "☺", (240, 140, 40))


# ═══════════════════════════════════════════════════════════════════════════
#  clock  (bold 5-row block font, drop shadow, per-cell contrast)
# ═══════════════════════════════════════════════════════════════════════════
_FONT = {
    "0": ["████", "█  █", "█  █", "█  █", "████"],
    "1": ["  █ ", " ██ ", "  █ ", "  █ ", " ███"],
    "2": ["████", "   █", "████", "█   ", "████"],
    "3": ["████", "   █", " ███", "   █", "████"],
    "4": ["█  █", "█  █", "████", "   █", "   █"],
    "5": ["████", "█   ", "████", "   █", "████"],
    "6": ["████", "█   ", "████", "█  █", "████"],
    "7": ["████", "   █", "  █ ", " █  ", " █  "],
    "8": ["████", "█  █", "████", "█  █", "████"],
    "9": ["████", "█  █", "████", "   █", "████"],
    ":": [" ", "█", " ", "█", " "],
}
_GLYPH_H = 5


def clock_width(t_str):
    return sum(len(_FONT[ch][0]) + 1 for ch in t_str) - 1


def draw_clock(scr, row, col, t_str, fg):
    blink = (time.time() % 1.0) < 0.5
    lit = []
    x = col
    for ch in t_str:
        glyph = _FONT[ch]
        gw = len(glyph[0])
        if not (ch == ":" and not blink):
            for dy, line in enumerate(glyph):
                for dx, g in enumerate(line):
                    if g != " ":
                        lit.append((x + dx, row + dy))
        x += gw + 1
    # bold glyph with per-cell contrast against the sky (no shadow)
    for cx, cy in lit:
        scr.put(cx, cy, "█", contrast_fg(fg, scr.bg_at(cx, cy)))


# ═══════════════════════════════════════════════════════════════════════════
#  main loop
# ═══════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════
#  overlay layout
# ═══════════════════════════════════════════════════════════════════════════
def layout_rows(h, night, greet):
    """Row numbers for the overlay, top-down, for a terminal `h` rows tall.

    Two spacings. ROOMY is the airy layout, for a tall window. COMPACT
    collapses the gaps and drops the divider, which is what makes the whole
    block fit a short window — a fullscreen terminal at a large font can
    easily be only ~26 rows. Either way the block is top-biased and kept
    clear of the treeline, whose tallest foliage starts at
    `h - 2 - len(tallest tree)`.
    """
    tree_top = h - 2 - tallest_tree(h)
    if h < 23:              # no room for the extras at this size — clock wins
        night = greet = False

    def build(top, roomy):
        L, r = {}, top
        L["clock"] = r
        r += _GLYPH_H + (2 if roomy else 1)      # blank row(s) under the clock
        L["date"] = r
        r += 1 + (1 if roomy else 0)             # date line + gap
        if night:
            L["moon"] = r
            r += 1
        if greet:
            if roomy:
                r += 1                           # blank row above the greeting
            L["greet"] = r
            r += 1
        if roomy:
            # divider keeps its original fixed offset below the date, so the
            # roomy layout is byte-for-byte the one that already looks right
            L["div"] = L["date"] + (6 if night else 5)
            L["panel"] = L["div"] + 2
        else:
            L["panel"] = r + 1
        L["bottom"] = L["panel"] + 3
        return L

    for roomy in (True, False):
        probe = build(1, roomy)
        span = probe["bottom"] - 1                       # rows below the clock
        top = max(1, min(h // 6, tree_top - 1 - span))   # top bias + clearance
        L = build(top, roomy)
        if L["bottom"] < tree_top or not roomy:
            return L


def run(scr):
    resized = {"flag": False}

    def on_winch(*_):
        resized["flag"] = True
    signal.signal(signal.SIGWINCH, on_winch)

    with _wx_lock:
        wx = dict(_wx)

    particles = []
    cur_spec_key = None
    effects = []
    scene_ts = 0.0
    scene = {}
    t0 = time.time()

    while True:
        if select.select([sys.stdin], [], [], 0)[0]:
            if sys.stdin.read(1):
                break

        if resized["flag"]:
            resized["flag"] = False
            scr._resize()
            particles = []
            cur_spec_key = None

        now = time.localtime(_clock())
        ts = time.time()
        t = ts - t0
        w, h = scr.w, scr.h
        horizon = h - 3

        # refresh derived scene every few seconds
        if ts - scene_ts > 4 or not scene:
            with _wx_lock:
                wx = dict(_wx)
            ok = wx.get("ok")
            # Real sun times win, even from a stale reading (a day-old sunrise
            # is a minute or two off); only with nothing cached at all do we
            # fall back to the computed almanac.
            if _OFFSET:
                # Previewing another date: wttr.in's sunrise/sunset are for the
                # real today, so use the almanac for the date being previewed.
                R, S = sun_times() or _FALLBACK_SUN
            else:
                try:
                    R, S = _hhmm(wx["sunrise"]), _hhmm(wx["sunset"])
                except Exception:
                    R, S = sun_times() or _FALLBACK_SUN
            cond = _FAKE_COND or (classify(wx.get("code", 113)) if ok else "clear")
            now_min = now.tm_hour * 60 + now.tm_min
            season = get_season(now.tm_mon)
            dt = datetime.date(now.tm_year, now.tm_mon, now.tm_mday)
            occ = get_occasion(dt)
            pal = apply_occasion(apply_condition(sky_palette(now_min, R, S),
                                                cond), occ)
            # Snow is real-weather only — no holiday fakes it. The display
            # should tell the truth about what is actually outside.
            snowy = cond == "snow"
            spec = particle_spec(cond, season, occ, pal)
            spec_key = (cond, season, occ.get("name"), spec["n"])
            if spec_key != cur_spec_key:
                particles = [Particle(w, h, spec) for _ in range(spec["n"])]
                cur_spec_key = spec_key
            else:
                for p in particles:
                    p.spec = spec
            night = pal["star"] > 0.25
            scene = dict(pal=pal, cond=cond, season=season, occ=occ,
                         snowy=snowy, night=night, ok=ok)
            scene_ts = ts

        pal = scene["pal"]
        occ = scene["occ"]

        # background gradient + stars
        ground_base = _SEASON_GROUND[scene["season"]]
        bg_rows = sky.bg_rows(w, h, horizon, pal, ground_base)
        scr.fill_bg(bg_rows, pal["txt"])
        sky.draw_stars(scr, horizon, pal, t)

        # ambient particles
        for p in particles:
            p.update(w, h)
            scr.put(int(p.x), int(p.y), p.ch, p.col)

        # storm lightning
        if scene["cond"] == "storm" and random.random() < 0.02:
            fy = random.randint(0, max(1, horizon - 2))
            fx = random.randint(2, max(3, w - 3))
            for k in range(random.randint(3, 7)):
                scr.put(fx + random.randint(-1, 1), fy + k, "╱", (235, 240, 210))

        # holiday effects
        if occ.get("fireworks") and random.random() < 0.05 and len(effects) < 120:
            effects.extend(spawn_firework(w, horizon))
        # Confetti: a lazy drift, not a blizzard. One piece every few frames
        # (was three *per* frame), a third of the old on-screen cap, and slow
        # enough to read individual pieces as they fall.
        if occ.get("confetti") and len(effects) < 32 and random.random() < 0.35:
            effects.append(Effect(random.uniform(0, w), 0,
                           random.uniform(-0.12, 0.12), random.uniform(0.10, 0.26),
                           random.choice("▪●*"), random.choice(_CONFETTI),
                           random.randint(80, 140), grav=0.003))
        if occ.get("bats") and random.random() < 0.03 and len(effects) < 40:
            by = random.randint(1, max(2, horizon // 2))
            effects.append(Effect(-1, by, random.uniform(0.4, 0.8),
                           random.uniform(-0.05, 0.05), "ᴧ", (40, 30, 45),
                           random.randint(40, 90)))
        if effects:
            alive = []
            for e in effects:
                if e.update() and 0 <= e.x < w and 0 <= e.y < h:
                    scr.put(int(e.x), int(e.y), e.ch, e.col)
                    alive.append(e)
            effects = alive

        # nature scene
        draw_scene(scr, pal, scene["season"], occ, scene["snowy"], t)

        # ── overlay: clock hero + panels ──────────────────────────────────
        t_str = time.strftime("%I:%M:%S", now)
        ampm = time.strftime("%p", now)
        clock_w = clock_width(t_str)
        greet = occ.get("greet")
        L = layout_rows(h, scene["night"], bool(greet))
        clock_row = L["clock"]
        clock_col = max(0, w // 2 - clock_w // 2)
        draw_clock(scr, clock_row, clock_col, t_str, pal["txt"])
        scr.text_a(clock_col + clock_w + 2, clock_row + 3, ampm, pal["acc"])

        # %-d is a GNU extension, so build the day number by hand for portability
        date_str = (time.strftime("%A  ·  %B ", now)
                    + f"{now.tm_mday}, " + time.strftime("%Y", now))
        if len(date_str) > w - 2:                    # narrow: shorter date
            date_str = (time.strftime("%a  ·  %b ", now)
                        + f"{now.tm_mday}, " + time.strftime("%Y", now))
        scr.text_a(max(0, w // 2 - len(date_str) // 2), L["date"], date_str,
                   pal["txt"])

        if "moon" in L:
            m_sym, m_name, m_pct = (lambda a: (a[2], a[0], a[1]))(moon_phase())
            ms = f"{m_sym}  {m_name}  ·  {m_pct}% lit"
            scr.text_a(max(0, w // 2 - len(ms) // 2), L["moon"], ms, pal["acc"])

        # occasion greeting
        if greet:
            gcol = mix(pal["acc"], (255, 255, 255), 0.2)
            scr.text_a(max(0, w // 2 - len(greet) // 2), L["greet"], greet, gcol)

        # divider (dropped in compact layouts to buy back a row)
        if "div" in L:
            dv = mix(pal["txt"], pal["top"], 0.5)
            dw = min(46, w - 4)
            scr.text_a(max(0, w // 2 - dw // 2), L["div"], "─" * dw, dv)

        panel_row = L["panel"]
        label = mix(pal["txt"], pal["acc"], 0.35)
        body = pal["txt"]

        # weather — centred under the clock
        with _wx_lock:
            wx = dict(_wx)
        if wx.get("ok"):
            u = wx.get("unit", "F")
            head = wx.get("place", "LOCAL WEATHER")
            if wx.get("stale"):
                head += "  ·  stale"
            lines = [
                (head, label),
                (f"{wx['temp']}°{u}  ·  feels {wx['feels']}°{u}", body),
                (wx["desc"], body),
                (f"H:{wx['hi']}°  L:{wx['lo']}°  ·  Humidity {wx['humid']}%", body),
            ]
        elif wx.get("ok") is False:
            lines = [("WEATHER UNAVAILABLE", (232, 96, 96))]
        else:
            lines = [("FETCHING WEATHER …", body)]
        for i, (text, col) in enumerate(lines):
            scr.text_a(max(0, w // 2 - len(text) // 2), panel_row + i, text, col)

        footer = "press any key to exit"
        scr.text_a(max(0, w // 2 - len(footer) // 2), h - 2, footer,
                   mix(pal["txt"], pal["top"], 0.55))

        scr.render()
        time.sleep(0.08)


sky = Sky()


# ═══════════════════════════════════════════════════════════════════════════
#  preview mode  (see any season / holiday without waiting for the calendar)
# ═══════════════════════════════════════════════════════════════════════════
# name -> ((month, day) or a callable(year) -> date, clock time to sit at)
_PREVIEWS = {
    "christmas":    ((12, 25),                              "20:00"),
    "newyear":      ((12, 31),                              "23:57"),
    "birthday":     (BIRTHDAY,                              "12:30"),
    "halloween":    ((10, 31),                              "21:00"),
    "thanksgiving": (lambda y: _nth_weekday(y, 11, 3, 4),   "12:30"),
    "july4":        ((7, 4),                                "21:30"),
    "easter":       (_easter,                                "13:00"),
    # seasons, for foliage/ground checks
    "winter":       ((1, 20),                               "12:30"),
    "spring":       ((4, 25),                               "12:30"),
    "summer":       ((7, 20),                               "12:30"),
    "fall":         ((10, 5),                               "12:30"),
}

_USAGE = """The Terminal Screensaver — a sky clock for your terminal

  screensaver                          live: real date, time and weather
  screensaver <name>                   preview an occasion or season
  screensaver --location "Oslo"        weather for somewhere else
  screensaver --units C                Celsius (or F)
  screensaver --date YYYY-MM-DD [--time HH:MM]
  screensaver --weather <cond>         force a sky condition
  screensaver --list                   show the preview names
  screensaver --help

Previews shift the whole scene's clock — sky gradient, moon phase, season,
holiday effects and the sun almanac all follow the faked date. Weather stays
live unless --weather is given.  Conditions: clear pcloudy cloudy fog rain
hrain storm snow.  Press any key to exit.

  screensaver christmas                ember-warm sky, lights in the trees
  screensaver easter                   pastel sky, flowers
  screensaver christmas --weather snow --time 18:30
  screensaver --location "Reykjavik" --units C

Defaults live in the CONFIGURATION block at the top of this file.
"""


def _next_occurrence(spec):
    """The soonest date matching a _PREVIEWS spec — this year, else next."""
    today = datetime.date.today()
    for year in (today.year, today.year + 1):
        d = spec(year) if callable(spec) else datetime.date(year, *spec)
        if d >= today:
            return d
    return today


def _parse_args(argv):
    """-> (offset_seconds, forced_condition, label) or raises SystemExit."""
    date = ttime = cond = name = None
    rest = list(argv)
    while rest:
        a = rest.pop(0)
        if a in ("-h", "--help"):
            print(_USAGE); raise SystemExit(0)
        elif a == "--list":
            print("preview names:\n  " + "\n  ".join(sorted(_PREVIEWS)))
            raise SystemExit(0)
        elif a == "--date" and rest:
            date = datetime.date(*map(int, rest.pop(0).split("-")))
        elif a == "--time" and rest:
            ttime = rest.pop(0)
        elif a == "--location" and rest:
            global LOCATION
            LOCATION = rest.pop(0)
        elif a == "--units" and rest:
            global UNITS
            u = rest.pop(0).upper()
            if u not in ("C", "F"):
                print("screensaver: --units takes C or F"); raise SystemExit(2)
            UNITS = u
        elif a == "--weather" and rest:
            cond = rest.pop(0)
            if cond not in ("clear", "pcloudy", "cloudy", "fog", "rain",
                            "hrain", "storm", "snow"):
                print(f"screensaver: unknown condition {cond!r}"); raise SystemExit(2)
        elif a in _PREVIEWS:
            name = a
            spec, default_time = _PREVIEWS[a]
            date = _next_occurrence(spec)
            ttime = ttime or default_time
        else:
            print(f"screensaver: unrecognised argument {a!r}\n"); print(_USAGE)
            raise SystemExit(2)

    if date is None and ttime is None:
        return 0.0, cond, None
    now = time.localtime()
    date = date or datetime.date(now.tm_year, now.tm_mon, now.tm_mday)
    hh, mm = (map(int, ttime.split(":")) if ttime else (now.tm_hour, now.tm_min))
    target = time.mktime((date.year, date.month, date.day, hh, mm, 0, 0, 0, -1))
    label = (f"{name or 'preview'}: {date:%a %b} {date.day} {date.year} "
             f"{hh:02d}:{mm:02d}" + (f", {cond}" if cond else ""))
    return target - time.time(), cond, label


def main():
    global _OFFSET, _FAKE_COND
    _OFFSET, _FAKE_COND, label = _parse_args(sys.argv[1:])
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("screensaver: needs a real terminal — run it directly, e.g.\n"
              "  ./screensaver.py")
        return
    threading.Thread(target=_fetch_wx, daemon=True).start()

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    sys.stdout.write("\033[?1049h\033[?25l\033[?7l\033[2J")  # alt screen, hide cursor, no-wrap, clear
    sys.stdout.flush()
    try:
        tty.setraw(fd)
        run(Screen())
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\033[0m\033[?7h\033[?25h\033[?1049l")  # reset, wrap, cursor, main screen
        sys.stdout.flush()
        if label:
            print(f"screensaver preview — {label}")


if __name__ == "__main__":
    main()
