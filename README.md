# ◉ ゼットプレイ — zplay

A very light, retro-Japanese **terminal music deck** for Arch Linux.
Pure Python + stdlib for the UI (no TUI framework), `mpv` for audio,
`ffmpeg` for spectrum analysis, Pillow for disc artwork.

```
zplay            # opens the app in your terminal
```

## Install

```bash
tar xf zplay.tar.gz && cd zplay
bash install.sh              # -> ~/.local/bin/zplay
# or system wide:
sudo bash install.sh --system  # -> /usr/bin/zplay
```

Dependencies (the installer offers to `pacman -S` anything missing):

| package | needed for |
|---|---|
| `mpv` | audio playback (required) |
| `ffmpeg` | frequency-bar analysis |
| `python-pillow` | images on the disc |
| `python-numpy` | real FFT bars (optional — falls back to an envelope analyser) |

Arch PKGBUILD included (`makepkg -si`).

First launch asks for a music folder (with tab completion).

## The three screens

**1 · ディスク DISC** — a rotating vinyl rendered with truecolour half-block
pixels. With no image it shows a vector *skeleton* label (dashed rings +
music-note glyph). Add images and they are mapped onto the label and spin
with the record. Transport row: `【<<】 【||】 【>>】`.

**2 · ハレツ VIZ** — frequency bars from a cached one-pass ffmpeg analysis
(64 log-spaced bands, 20 fps), with peak caps and optional mirroring.

**3 · セッテイ CONF** — settings: music folders, images, disk style, rotation,
theme, effects, shuffle/repeat, volume, fps. `↑↓` move, `←→` change, `↵` apply.

## Keys

| key | action |
|---|---|
| `1` `2` `3` / `Tab` | switch screens |
| `space` | play / pause |
| `n` `p` | next / previous track |
| `← →` | seek 5 s |
| `+ -` | volume |
| `t` `T` | next / previous colour theme |
| `i` | switch disc image now |
| `d` | disk style circle ↔ square |
| `r` | rotation on / off |
| `s` `l` | shuffle / repeat |
| `m` | mirrored bars |
| `z` | zen mode (hide all chrome) |
| `?` `q` | help / quit |

## CLI commands

Every operation also works from the shell — mpv stays alive in the
background, so these control the running player.

```
playback   play [query|#] · pause · resume · toggle · next · prev · stop
           seek ±SECS · volume [0-130] · shuffle [on|off] · repeat [off|all|one]
           status · list [n] · search QUERY
library    add-folder PATH · folders · remove-folder PATH|# · scan
images     add-image PATH... · images · remove-image PATH|# · clear-images
           image-mode [random|sequence|off]
look       theme [name] · themes · disk [circle|square] · rotate [on|off]
           speed [0.1-4.0] · bars [n|auto] · set KEY VALUE · config
misc       doctor · version · help
```

Examples:

```bash
zplay add-folder ~/Music
zplay add-image ~/Pictures/covers      # a whole folder of art
zplay theme rainbow
zplay disk square
zplay play "lofi"
zplay next
```

## 20 bar colour themes

`sakura` `ume` `momo` (pink family) · `matcha` `take` `mint` (green family) ·
`sora` `ai` `ruri` (blues) · `fuji` `murasaki` `lavender` (purples) ·
`yuyake` `hinode` `kohaku` `kin` `sango` (warm) · `kuro` (mono) ·
`rainbow` (hue sweep) · `multi` (per-bar multicolour)

`zplay themes` prints live swatches.

## Extra touches

- beat-reactive disc pulse
- sakura petal rain overlay
- glow sheen + vinyl groove grain on the record
- peak caps and mirrored bars
- zen mode, ASCII-only mode for minimal terminals
- spectrum cache in `~/.cache/zplay` so each track is analysed once

Config lives in `~/.config/zplay/config.json`, images are copied to
`~/.local/share/zplay/images`.
