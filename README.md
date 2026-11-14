# Make the AI judge happy — make.fun entry

Bounty: https://make.fun/bounty/ai-happy-01
($250, ends Sun 15 Nov 2026 00:00 WITA; 100 paid places, 1st $50.)

## What this is

`main.py` is a program that writes one image to `/output/entry.png`:
a golden-hour scene with a joyful puppy, sunflowers, butterflies and
floating hearts, made to make the AI judge happy.

## How to run

```sh
python3 main.py            # writes /output/entry.png
OUTPUT_PATH=./out.png python3 main.py   # custom output path (testing)
```

## Constraints (per the bounty brief)

- **Python 3.13 standard library only** — no Pillow, no third-party
  packages. The grading container installs nothing.
- **No network.** The program runs twice and both runs write
  identical bytes (verified: same SHA-256 across runs).
- Output: one whole PNG, 1024x1024, ~48 KB (limit: 1 MiB, 1024x1024).

## How it works

- The PNG is encoded by hand (`zlib` + `struct`: IHDR/IDAT/IEND,
  no timestamps, deterministic).
- The scene is drawn procedurally on a `bytearray` canvas with
  scanline fills (rectangles, circles, ellipses, polygons, arcs,
  gradients) — no per-pixel Python loops over the whole image.
- Drawn at 2x (2048x2048) and downscaled with a 2x2 box average
  for smooth edges. Runtime ~1.2 s on one CPU (limit: 60 s).

## Fallback

If generation fails for any reason, the program copies the bundled
`entry.png` (the same image, generated locally) to the output path.
The brief explicitly allows a program that copies an image the
repository holds.

## Files

- `main.py` — the entry program (stdlib only)
- `entry.png` — the generated image (also the fallback asset)
- `main_pil_draft.py`, `entry_pil_draft.png` — an earlier iteration
  built with Pillow, kept for reference (NOT used by `main.py`)

## License

MIT — see `LICENSE`.
