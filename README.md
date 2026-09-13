# The Terminal Screensaver

A "screensaver" that runs in your terminal. Complete with time, weather,
seasons, and night/day cycles. Modify as needed to fit your location and needs.
**No API key needed.**

This is something simple, neat, and nice to look at if you have an extra screen while working, or want something up as a screensaver. 

A big clock sits over a sky that actually matches the time of day outside —
sunrise oranges, blue afternoon, sunset, then stars — along with your local
weather, the moon phase, and a treeline that changes with the seasons and lights
up for the holidays.

It is **one Python file**, with **nothing to install**.

```
                        ████ █  █   ████ ████   ████ ████
                        █  █ █  █   █       █      █    █
                        █  █ ████   ████   █     ███  ███                      ❦
                        █  █    █      █  █        █    █  PM
                 ❦      ████    █   ████  █     ████ ████
        ,
                 ❦        Sunday  ·  September 13, 2026
                                                ❦
             ,                    OSLO, NORWAY~                              ✽
                               14°C  ·  feels 12°C
                                  Partly cloudy
                          H:17°  L:9°  ·  Humidity 68%
     ▒▓▓▒  ✽  ~       ~                                               ▒▓▓▒
    ▓▓▓▓▓▒                                 ~               ,         ▓▓▓▓▓▒
   ▓▓▓▓▓▓▓▓~   ▒▓▒    ▒▓▒                            ▒▓▒     ▒▓▒    ▓▓▓▓▓▓▓▓
  ▒▓▓▓▓▓▓▓▓▒  ▓▓▓▓▒  ▓▓▓▓▒     ~     ❦       ,      ▓▓▓▓▒   ▓▓▓▓▒  ▒▓▓▓▓▓▓▓▓▒
   ▓▓▓▓▓▓▓▓  ▒▓▓▓▓▓ ▒▓▓▓▓▓                         ▒▓▓▓▓▓  ▒▓▓▓▓▓   ▓▓▓▓▓▓▓▓
    ▒▓█▓█▓▒   ▒▓█▓   ▒▓█▓                           ▒▓█▓    ▒▓█▓     ▒▓█▓█▓▒
✽|ⵦⵦⵦ█ⵦ▐█/ⵦⵦⵦ‸ⵦ|█\ⵦⵦⵦⵦⵦ█\\ⵦⵦⵦⵦⵦ///ⵦⵦⵦⵦⵦ//||ⵦⵦⵦⵦ\\\\ⵦⵦⵦ█ⵦ|||ⵦⵦⵦ█ⵦ///ⵦⵦⵦ█ⵦ▐█\ⵦ\ⵦⵦ
                              press any key to exit
```

*(That is a real frame with the color stripped out — color is most of the point,
so this picture undersells it badly.)*

---

## Quick start

You need Python 3.8 or newer, which almost every Mac and Linux machine already
has. Open a terminal and:

```bash
git clone https://github.com/conrad97/The-Terminal-Screensaver.git
cd The-Terminal-Screensaver
chmod +x screensaver.py
./screensaver.py
```

Press **any key** to quit.

That's it. It figures out roughly where you are from your internet connection,
so the weather and the sunrise should already be right.

If `./screensaver.py` complains, try `python3 screensaver.py` instead.

---

## What you're looking at

### The sky

The sky is not a day picture and a night picture — it slides continuously
through fourteen stages, pinned to the **real** sunrise and sunset times for
your location. Deep night, the first blue before dawn, pre-dawn reds, sunrise
orange, full daylight, late afternoon, sunset, afterglow, back to night. Stars
fade in as it darkens and twinkle.

### The moon

At night you get the moon's phase and how lit it is, like
`◑  Waning Gibbous  ·  95% lit`. This is calculated on your machine, so it works
with no internet at all.

### The weather

Real conditions for your location, refreshed every five minutes. The weather
changes both the sky color and what falls through the air:

| Weather | What you see |
|---|---|
| Clear | Nothing falling. Stars at night |
| Partly cloudy / cloudy | Grey sky, a few slow drifting specks |
| Rain | Grey-blue sky, falling drops |
| Heavy rain | Darker, faster, more of them |
| Thunderstorm | Dark green-grey sky, heavy streaks, **lightning bolts** |
| Snow | Pale sky, drifting flakes, **snow settles on the trees and grass** |
| Fog | Flat grey wash and a haze of dots |

### The seasons

| Season | Months | What changes |
|---|---|---|
| **Spring** | Mar–May | Fresh green ground and grass, **wildflowers** in the grass |
| **Summer** | Jun–Aug | Dry golden-green grass, deep green trees |
| **Fall** | Sep–Nov | Brown-gold ground, and **leaves falling** whenever it isn't raining |
| **Winter** | Dec–Feb | Grey-blue ground, bare colors, trees go bronze |

*(Those months are the northern hemisphere. If you're in the southern
hemisphere, see [Flip the seasons](#flip-the-seasons-southern-hemisphere).)*

### The holidays

On these dates the scene changes by itself:

| Occasion | When | What happens |
|---|---|---|
| **Christmas** | Dec 18–30 | Twinkling colored lights strung through the trees, and the sky glows warm after dark |
| **New Year** | Dec 31 – Jan 2 | Confetti drifting down |
| **Halloween** | Oct 25–31 | Jack-o-lanterns in the grass, bats flapping across the sky |
| **Thanksgiving** | 4th Thursday of Nov, ±3 days | Nearly double the falling leaves |
| **Independence Day** | Jul 3–5 | Fireworks bursting over the treeline |
| **Easter** | Easter Sunday, ±3 days | Soft pastel sky and flowers |
| **Birthday** | whatever you set | Confetti and a greeting |

Each one also puts a line of text under the date, like *Merry Christmas*.

### See any of them right now

You don't have to wait for December. Any holiday or season can be summoned:

```bash
./screensaver.py christmas
./screensaver.py halloween
./screensaver.py july4
./screensaver.py winter
```

Full list: `./screensaver.py --list`

You can also force the weather and the time of day, which is the fun part:

```bash
./screensaver.py --weather storm                    # lightning, right now
./screensaver.py christmas --weather snow           # a white Christmas
./screensaver.py --time 06:45                       # pre-dawn reds
./screensaver.py --time 22:00                       # stars
./screensaver.py --date 2026-12-21 --time 17:35     # winter solstice sunset
```

This is also the easiest way to check any change you make — jump straight to the
thing you edited instead of waiting for the calendar.

---

## Make it your own

**Everything you need is in one block at the very top of the file.** You do not
need to understand the rest.

### How to edit the file

Open `screensaver.py` in any text editor — TextEdit, Notepad, VS Code, `nano`,
whatever you like. Scroll to the top. Just below the opening description you'll
find:

```python
# ═══════════════════════════════════════════════════════════════════════════
#  CONFIGURATION  — edit this block, that is the whole setup
# ═══════════════════════════════════════════════════════════════════════════
```

Change the values, save, and run it again. That's the entire loop.

Two things worth knowing before you start:

- **Keep the quotes.** `LOCATION = "Oslo"` is right; `LOCATION = Oslo` will
  break it. Text needs quotes, numbers don't.
- **You cannot permanently break anything.** If it stops working, you have a
  pristine copy one command away: `git checkout screensaver.py` throws away
  your edits and restores the original.

### 1. Your location

This is the one most people want. Find:

```python
LOCATION = ""
```

Empty means "guess from my internet connection," which is usually close enough.
To pin it exactly, put a place between the quotes:

```python
LOCATION = "Oslo"              # a city
LOCATION = "Boulder,CO"        # add the state/region if the name is ambiguous
LOCATION = "Kyoto"
LOCATION = "~Mount Fuji"       # a ~ in front means "this landmark"
LOCATION = "~LHR"              # an airport code
LOCATION = "48.85,2.35"        # exact coordinates, latitude then longitude
```

The name shown on screen comes back from the weather service, so it will match
what you asked for.

To try somewhere without editing anything:

```bash
./screensaver.py --location "Reykjavik"
```

### 2. Fahrenheit or Celsius

```python
UNITS = "F"        # change to "C" for Celsius
```

Or try it with `./screensaver.py --units C`.

### 3. Your birthday

```python
BIRTHDAY = (6, 15)        # (month, day) — June 15
BIRTHDAY_NAME = ""
```

The first number is the month, the second is the day. So the 3rd of November is
`(11, 3)`. Put your name in the quotes to get *Happy Birthday, Sam!* instead of
just *Happy Birthday!*:

```python
BIRTHDAY = (11, 3)
BIRTHDAY_NAME = "Sam"
```

Don't want it at all? `BIRTHDAY = None`

Check it with `./screensaver.py birthday`.

### 4. Sun times when the internet is down (optional)

Sunrise and sunset normally come from the weather service, and the program
calculates them itself as a backup. It picks up your coordinates automatically
the first time the weather loads — so for most people **this needs no
attention**.

If your machine is often offline and you want the sky to still be right, fill
these in:

```python
LATITUDE = 59.91
LONGITUDE = 10.75
```

To find your numbers: search "my latitude longitude", or right-click your spot
in Google Maps — the first number is latitude, the second longitude. **Keep the
minus signs.** Most of the Americas have a negative longitude; anywhere south of
the equator has a negative latitude.

---

## Going further

Optional, and a little more adventurous. Everything below is still just editing
text in the same file.

### Add your own occasion

Say you want your local festival, an anniversary, or a name day. Find the
function called `get_occasion` (search the file for `def get_occasion`). Inside
it you'll see a list of dates, each one looking roughly like this:

```python
    # Halloween
    if m == 10 and 25 <= d <= 31:
        return dict(name="halloween", greet="Happy Halloween",
                    pumpkins=True, bats=True)
```

Read that as: *if the month is 10 (October) and the day is between 25 and 31,
say "Happy Halloween" and turn on pumpkins and bats.*

Near the bottom of that function there's a spot marked for your own. Copy the
pattern:

```python
    if m == 5 and 1 <= d <= 5:
        return dict(name="spring_fair", greet="Spring Fair", flowers=True)
```

Here's everything you can turn on:

| Write this | And you get |
|---|---|
| `greet="Some text"` | That line under the date |
| `lights=True` | Twinkling colored lights in the trees |
| `pumpkins=True` | Jack-o-lanterns along the grass |
| `bats=True` | Bats flying across |
| `confetti=True` | Confetti drifting down |
| `fireworks=True` | Fireworks over the treeline |
| `flowers=True` | Wildflowers in the grass |
| `heavy_leaves=True` | Much heavier leaf fall |
| `warm=True` | Warm ember glow in the sky, strongest after dark |
| `pastel=True` | Soft pastel sky, daytime only |

Mix as many as you like. One rule: **the first matching date wins**, so if two
occasions overlap, put the more specific one higher up.

To preview it instantly, add it to the `_PREVIEWS` list further down the file:

```python
    "spring_fair":  ((5, 3), "13:00"),
```

Then `./screensaver.py spring_fair`.

**Don't want a holiday?** Delete its `if` block, or just put a `#` at the start
of each of its lines. They're all independent.

### Flip the seasons (southern hemisphere)

Find `def get_season` and swap the month groups:

```python
def get_season(month):
    if month in (6, 7, 8):   return "winter"     # was 12, 1, 2
    if month in (9, 10, 11): return "spring"     # was 3, 4, 5
    if month in (12, 1, 2):  return "summer"     # was 6, 7, 8
    return "fall"
```

### Change the trees

Search for `_CONIFERS`. They're drawn as plain text — three trees, large,
medium and small:

```python
    (   # 2 — small sapling
        "   ▒▓▒ ",
        "  ▓▓▓▓▒",
        " ▒▓▓▓▓▓",
        "  ▒▓█▓ ",
        "    █  ",
    ),
```

`▓` and `▒` are foliage (`▒` reads as a lighter, raggedy edge), `█` is trunk.
Edit the pictures however you like — palms, poplars, cacti, mushrooms. **Keep
every line in one tree the same length** and it will behave.

### Change the colors

Colors are `(red, green, blue)`, each 0–255. A few good places to fiddle:

| Search for | Controls |
|---|---|
| `_SEASON_GRASS` | Grass color in each season |
| `_SEASON_GROUND` | Ground color in each season |
| `_anchors` | The whole sky, stage by stage |
| `_CONFETTI` | Confetti colors |
| `top=` / `hor=` in `_anchors` | Sky at the top of the screen / at the horizon |

Preview a specific time to see a sky change immediately:
`./screensaver.py --time 19:35`

### Make it faster or slower

At the very end of the `run` function:

```python
        time.sleep(0.08)      # smaller = smoother and busier, larger = calmer
```

### Too much stuff falling?

Find `particle_spec`. Each weather type has an `n=` number — that's how many
things are in the air. Lower it for a calmer scene:

```python
    if cond == "rain":
        return dict(n=60, ...)      # try n=30
```

---

## Run it automatically when you step away

To have it appear after five minutes of an idle terminal, add this to your
`~/.bashrc` (adjust the path):

```bash
TMOUT=300
trap '/path/to/screensaver.py; TMOUT=300' ALRM
```

You may also want it on your `PATH` so you can run it from anywhere by typing
`screensaver`:

```bash
ln -s "$PWD/screensaver.py" ~/.local/bin/screensaver
```

---

## If something looks wrong

**Boxes, question marks or blank squares instead of trees and stars.** Your font
is missing some characters, or your terminal isn't set to UTF-8. Try a font like
DejaVu Sans Mono, JetBrains Mono, Iosevka or Hack.

**The colors look flat or banded.** Your terminal doesn't do full color. Test
with:

```bash
printf '\033[38;2;255;100;0mTEST\033[0m\n'
```

That should print an orange `TEST`. If it's grey, try Kitty, WezTerm,
Alacritty, iTerm2, Windows Terminal or a recent GNOME Terminal / Konsole.

**"needs a real terminal"** — it's being piped somewhere, or run from something
that isn't a terminal. Run it directly in a terminal window.

**"WEATHER UNAVAILABLE"** — no weather for 30 minutes. The service is free and
sometimes rate-limits; it retries on its own. Test with
`curl 'https://wttr.in/?format=j1'`. The clock, sky and moon keep working
regardless.

**Sunrise seems an hour or two off.** Usually your computer's timezone
disagreeing with the location you configured. It corrects itself after the first
weather refresh. If it persists, set `LATITUDE`/`LONGITUDE` explicitly.

**Everything overlaps in a small window.** Below roughly 20 rows there isn't
room for the clock, the text and the trees. Make the window taller, or the font
smaller.

**A preview doesn't look festive.** Previews keep using *live* weather, so
`christmas` on a sunny day is a sunny Christmas. Add `--weather snow`.

**I broke it.** `git checkout screensaver.py` restores the original file.

---

## For the curious: how it works

Not required reading.

The screen is a grid of characters. Each frame the program builds the picture
into a buffer — sky gradient first, then stars, then anything falling, then the
trees and grass, then the clock and text on top — and compares it to the
previous frame, sending only the characters that actually changed. That is why a
full-screen animation in a terminal doesn't hammer your CPU.

Weather runs on a background thread so a slow network never stutters the
animation. Sunrise and sunset come from the weather service when available; when
not, they're computed from your coordinates with standard solar-position math,
accurate to a minute or two. If the weather service goes quiet, the last good
reading keeps showing (marked `· stale`) for half an hour rather than blanking
out.

The layout measures your terminal and adapts: a tall window gets airy spacing
with a divider line, a short one tightens up and drops the divider, and the
trees shrink a size class so they don't eat the whole frame. The text is always
kept clear of the treeline.

Requirements are deliberately tiny: Python 3.8+, standard library only, a
terminal with 24-bit color and a UTF-8 locale. No pip, no config file, no
dependencies to go stale. Works on Linux, macOS and BSD.

---

## License

MIT — do what you like with it. See [LICENSE](LICENSE).

Weather data from [wttr.in](https://wttr.in).
