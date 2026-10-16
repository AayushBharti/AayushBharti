# Profile GIF

`aayush-reveal.gif`: an animated profile picture for Gmail and similar sites. It is 400×400, loops every 8 seconds and is about 550KB.

The first frame is the plain photo, so sites that keep only the first frame still show a clean picture.

## What it does

1. The photo holds for a few seconds.
2. An iris closes on the photo while A and B fly in from opposite sides.
3. The letters lock together and a blue backlight flares, then settles to a soft glow. A light sweeps across the logo.
4. The letters split apart while the iris opens back onto the photo. The outro is the intro reversed.

## Rebuild

```bash
./build.sh
```

You need `ffmpeg`, `rsvg-convert` (`brew install ffmpeg librsvg`), `python3` and `bun`. The script sets up Pillow and numpy in a local venv, and gets gifsicle from npm. Scratch files go to `build/`.

## Files

- `render.py`: draws each frame at 800px. Timing, glow, sweep and motion blur all live here.
- `build.sh`: renders the frames, then encodes and compresses the GIF.
- `src/aayush.webp`: the photo (the same one as on the site's lanyard badge).
- `src/A.svg`, `src/B.svg`: the two halves of the logo. The `viewBox` sets the logo's size and position.

## Tweaks

- **Logo size:** change the `viewBox` width and height in both SVGs. It is currently `9000`, which makes the logo 55% of the width. A smaller number makes the logo bigger. Move the x and y offsets by half the size change to keep it centred.
- **Timing:** see `letters_layer()` for the letters, `close` and `reopen` in `frame()` for the iris, and `glow_amt()` for the glow.
- **File size:** the photo palette and the lossless photo frames protect skin and lip colour, so don't add lossy compression to the intro or outro.
