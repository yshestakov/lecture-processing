#!/usr/bin/env bash
# Run the lecture toolbox with the current directory mounted at /work.
#
#   ./docker-run.sh                                   # interactive shell
#   ./docker-run.sh lecture.sh probe -c 1238:804:342:0 lecture.mp4
#   IMAGE=lecture-agent ./docker-run.sh pi            # agent layer (Pi or opencode)
#
# Whisper models are cached in the docker volume "lecture-models" (≈1.6 GB for large-v3-turbo).
set -euo pipefail

IMAGE="${IMAGE:-lecture-tools}"
args=(--rm -v "$PWD":/work -w /work -v lecture-models:/models)
[[ -t 0 && -t 1 ]] && args+=(-it)

if [[ "$(uname -s)" == Linux ]]; then
  args+=(--user "$(id -u):$(id -g)")
  # VA-API (Intel/AMD iGPU) for h264_vaapi; build the image with --build-arg VAAPI=1
  if [[ -e /dev/dri/renderD128 ]]; then
    args+=(--device /dev/dri --group-add "$(stat -c %g /dev/dri/renderD128)")
  fi
fi

# Pass API keys for the agent layer, only if they are set
for v in ANTHROPIC_API_KEY OPENAI_API_KEY GROQ_API_KEY OPENROUTER_API_KEY GEMINI_API_KEY; do
  [[ -n "${!v:-}" ]] && args+=(-e "$v")
done

[[ $# -gt 0 ]] || set -- bash
exec docker run "${args[@]}" "$IMAGE" "$@"
