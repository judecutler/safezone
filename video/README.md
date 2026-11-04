# Demo video build

Everything except the two phone clips is code.

1. `node video/capture.cjs <dir>` captures app screens from a server running the recorded demo.
2. `python video/tts.py <models> video/lines.json <vo dir> af_heart` speaks `lines.json` with Kokoro (model files from the kokoro-onnx GitHub release, word pronunciations from the misaki dictionaries, extra words in `pron.json`).
3. `python video/build_timeline.py <vo dir> <stage>/timeline.json` times every scene to its narration.
4. Serve the stage folder (`stage.html`, `timeline.json`, `assets/`) on port 8765, then `node video/render.cjs <stage> <scenes dir>` renders one mp4 per scene (`--stills t1,t2` renders single frames to check).
5. `python video/mix.py <timeline> <vo dir> react.wav phone.wav mix.wav` builds the soundtrack.
6. Join the scenes with the ffmpeg concat demuxer (`-c copy`), add `mix.wav` with `loudnorm=I=-15:TP=-1.5`.
