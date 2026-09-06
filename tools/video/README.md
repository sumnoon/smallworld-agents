# Intro video production

The introduction combines the application's actual Canvas renderer, a recorded offline simulation, local synthetic narration, open captions, and an original procedural musical score. It does not record the user's saved town or make model requests. The Ollama segment explains an available mode; all footage is explicitly labeled as a guided offline demo with condensed simulation time.

The delivery segment uses real world states and verifies that Samir transfers the coffee into Elena's inventory. The ending is held so the completed task is visible. This is a staged introduction, not a live-model benchmark or a recording of browser controls.

## Sources

- `storyboard.json`: narration, captions, headings, and minimum scene durations.
- `record_demo.py`: records a fresh in-memory town into `.video-build/demo.json`.
- `narrate.ps1`: generates narration with a locally installed Windows speech voice (Zira Desktop when available).
- `mix_audio.py`: aligns narration and creates a quiet C/Am/F/G arpeggio score.
- `render_intro.mjs`: renders the actual `SmallworldRenderer`, composes the introduction, and encodes H.264/AAC MP4.

The rendered video, poster, and transcript are in `docs/media/`. Intermediate files and optional tool installations are ignored by Git. Re-rendering can vary slightly with operating-system fonts, installed voices, and asynchronous offline decisions.

## Rebuild on Windows

Requires Python 3.11+, NumPy, Node.js 22+, `@napi-rs/canvas`, FFmpeg, and Windows System.Speech. These are optional media-production dependencies; the application itself still requires no third-party packages.

One way to isolate the tooling:

```powershell
python -m pip install --target .video-tools numpy imageio-ffmpeg
npm install --prefix .video-tools --no-save @napi-rs/canvas
$env:PYTHONPATH = (Resolve-Path .video-tools).Path
$env:VIDEO_CANVAS_MODULE = (Resolve-Path .video-tools/node_modules/@napi-rs/canvas).Path
$env:VIDEO_FFMPEG = (Get-ChildItem .video-tools/imageio_ffmpeg/binaries/*.exe | Select-Object -First 1).FullName

python tools/video/record_demo.py
./tools/video/narrate.ps1
python tools/video/mix_audio.py
node tools/video/render_intro.mjs
```

The MP4 uses 1280 × 720 resolution, 24 fps, H.264 video, AAC audio, and fast-start metadata. The final file is also uploaded as a GitHub video attachment so the README can display it as a playable introduction. The transcript provides a text alternative to the narration.
