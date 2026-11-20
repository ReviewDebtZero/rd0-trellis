# Demo

`assets/demo.gif` is a typed replay of real `trellis audit` and `trellis scan` output on
`packages/rd0-trellis/examples` (captured in `src/audit.txt` and `src/scan.txt`). The recorder is
copied from rd0-jinx.

## Rebuild

Needs Python with `playwright` and `Pillow`, Chrome, and `ffmpeg`. Set the Chrome path in `src/rec_one.py`.

```bash
cd packages/rd0-trellis
trellis audit examples/repo | sed -n '1,9p' > ../../assets/video/src/audit.txt
trellis scan examples/agent_pr.diff --config examples/trellis.toml --title "Load theme from prefs" \
  | grep -vE '^\s+(evidence|\|)' > ../../assets/video/src/scan.txt
cd ../../assets/video/src
python3 gen_term.py && python3 rec_one.py term term.html 16
ffmpeg -y -i term.mp4 -vf "fps=12,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer" ../../demo.gif
```
