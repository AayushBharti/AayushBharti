#!/usr/bin/env bash
# Build aayush-reveal.gif (400x400, 8s loop, ~550KB) from src/.
# Needs: ffmpeg, rsvg-convert (brew install ffmpeg librsvg), python3, bun.
# Output: ./aayush-reveal.gif. Scratch files go to ./build (gitignored).
set -euo pipefail
cd "$(dirname "$0")"

for bin in ffmpeg rsvg-convert python3 bun; do
  command -v "$bin" >/dev/null || { echo "ERROR: $bin not found" >&2; exit 1; }
done

B=build
mkdir -p "$B"

# Tools: Pillow/numpy in a local venv; gifsicle via npm (no Xcode needed).
[ -x "$B/.venv/bin/python" ] || { python3 -m venv "$B/.venv" && "$B/.venv/bin/pip" -q install pillow numpy; }
[ -x "$B/gs/node_modules/gifsicle/vendor/gifsicle" ] || { mkdir -p "$B/gs" && (cd "$B/gs" && bun add gifsicle@7 >/dev/null); }
GS="$B/gs/node_modules/gifsicle/vendor/gifsicle"
PY="$B/.venv/bin/python"

# Assets: logo halves (same placement) and the square photo crop.
for n in A B; do rsvg-convert -w 800 -h 800 "src/$n.svg" -o "$B/${n}800.png"; done
ffmpeg -v error -y -i src/aayush.webp -vf "crop=1760:1760:107:40,scale=1000:1000:flags=lanczos" -frames:v 1 -update 1 "$B/photo1000.png"

# Frames: 160 @ 20fps, rendered in 8 parallel chunks.
rm -rf "$B/frames"
for s in 0 20 40 60 80 100 120 140; do "$PY" render.py "$s" $((s + 20)) >/dev/null & done
wait
F="$B/frames/f%04d.png"
VF="scale=400:400:flags=lanczos,unsharp=5:5:0.45:5:5:0"

# Palettes: the photo frames take colours from the photo weighted toward the
# face (keeps skin and lip tones); the logo frames get their own.
ffmpeg -v error -y -i "$B/frames/f0000.png" -filter_complex \
  "[0]${VF},split[a][b];[b]crop=200:200:100:80,scale=400:400[f];[a][f]hstack,palettegen=max_colors=256:stats_mode=full" \
  -frames:v 1 -update 1 "$B/pal_face.png"
ffmpeg -v error -y -framerate 20 -start_number 66 -i "$F" -frames:v 60 \
  -vf "${VF},palettegen=max_colors=256:stats_mode=full" -update 1 "$B/pal_logo.png"

# enc <name> <first frame> <count> <palette> <dither> [lossy]
enc() {
  ffmpeg -v error -y -framerate 20 -start_number "$2" -i "$F" -i "$4" -frames:v "$3" \
    -filter_complex "[0]${VF}[x];[x][1]paletteuse=dither=$5:diff_mode=rectangle" "$B/$1.gif"
  "$GS" -O3 ${6:+--lossy=$6} "$B/$1.gif" -o "$B/o_$1.gif"
}
enc intro 0 66 "$B/pal_face.png" sierra3        # photo + iris close + letters in (lossless)
enc logo 66 60 "$B/pal_logo.png" none 80         # glow, sweep, hold
enc outro 126 14 "$B/pal_face.png" sierra3 60    # split + iris open

# The last 1s (photo hold) equals frame 0, so drop it and hold frame 0 1s
# longer instead. Concatenate without -O: re-optimising across palettes bloats it.
D0=$("$GS" --info "$B/o_intro.gif" | grep -m1 -A1 "image #0" | grep -oE "delay [0-9.]+" | grep -oE "[0-9.]+")
D0=$(python3 -c "print(round(($D0 + 1.0) * 100))")
"$GS" "$B/o_intro.gif" -d"$D0" "#0" --same-delay "#1-" -o "$B/o_intro_d.gif"
"$GS" --loopcount=forever "$B/o_intro_d.gif" "$B/o_logo.gif" "$B/o_outro.gif" -o aayush-reveal.gif 2>/dev/null

echo "INFO: aayush-reveal.gif $(($(wc -c < aayush-reveal.gif) / 1024))KB"
