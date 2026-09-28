# process — lecture video → Obsidian notes

Everything needed to turn a recorded lecture into notes: the scripts, a Docker image with the tools, and the agent skill for the LLM steps. The full write-up of how and why is in [process.md](process.md); the diagram is [pipeline.svg](pipeline.svg).

## Layout

```
process/
├── README.md               this file
├── process.md, pipeline.svg, Lecture processing.pdf    the process, step by step
├── AGENTS.md               vault conventions for coding agents (language, markers, Obsidian links)
├── Dockerfile              tools image; `--target agent` adds Node, Pi and OpenCode
├── docker-run.sh           runs the image with the current folder mounted at /work
├── requirements.txt        Python packages (faster-whisper, scenedetect, imagehash, …)
├── scripts/
│   ├── lecture.sh          pipeline driver: probe | audio | transcribe | proxy | scenes | slides | build | check | all
│   ├── transcribe.py       faster-whisper → "[start → end]  text" lines
│   ├── extract_slides.py   one image per scene from the original video, slides/index.csv
│   ├── build_lecture_md.py transcript + slide index → lecture.md (--obsidian)
│   ├── dump_slides.py      compact, chunked dump of lecture.md for LLM reading
│   └── check_links.py      verifies Obsidian links; exit 1 on broken links
├── skills/lecture-to-notes/
│   ├── SKILL.md            the LLM half: Q & A digest, topic notes, references
│   └── templates/          topics_template.md, qa_digest_template.md
└── legacy/                 one-off scripts from the first lectures (kept for reference)
```

## Quick start (local, with the existing `.venv`)

```bash
source ../.venv/bin/activate
S=process/scripts            # from the vault root

$S/lecture.sh probe -c 1238:804:342:0 Course/lecture.mp4    # check probe.png / check.png
$S/lecture.sh all -c 1238:804:342:0 -e 3:52:37 \
   -p "Лекція про Harness в агентах типу Codex, Claude Code, Pi" \
   -t "Harness Engineering, частина 1" Course/lecture.mp4
```

Outputs go to `Course/lecture/`:
- `audio.wav`
- `transcript.txt`
- `proxy.mp4`
- `scenes.csv`
- `slides/`
- `lecture.md`

Steps whose output exists are skipped; `-f` redoes them. `lecture.sh -h` lists all options.

## Docker

```bash
cd process
docker build -t lecture-tools .                          # add --build-arg VAAPI=1 for h264_vaapi on Linux
cd ../Harness_Engineering
../process/docker-run.sh lecture.sh all -c 1238:804:342:0 lecture.mp4
```

- Whisper models are cached in the `lecture-models` volume. The first run downloads about 1.6 GB for large-v3-turbo.
- **On macOS, Docker has no GPU access.** Transcription runs on CPU (int8), and the proxy uses libx264 instead of VideoToolbox. For long lectures, the native `.venv` on the Mac is faster. The container is for Linux boxes and reproducibility.
- On Linux with an Intel or AMD iGPU, `docker-run.sh` passes `/dev/dri` through, and `lecture.sh` picks `h264_vaapi` automatically.

## Agent layer (optional)

```bash
docker build -t lecture-agent --target agent .
IMAGE=lecture-agent ANTHROPIC_API_KEY=… ../process/docker-run.sh pi        # or: opencode
```

- The image has Node 22, [Pi](https://github.com/earendil-works/pi) (`@mariozechner/pi-coding-agent`) and [OpenCode](https://opencode.ai/docs/) (`opencode-ai`). Change them with `--build-arg AGENT_PACKAGES="…"`.
- The `lecture-to-notes` skill is installed in `~/.agents/skills/`, which both agents read. `AGENTS.md` is installed as their global instructions.
- API keys are passed from the environment at run time and never stored in the image.
- **Claude Code / Cowork:** copy or symlink `skills/lecture-to-notes` into `~/.claude/skills/` (or the vault's `.claude/skills/`). The same SKILL.md works there.
