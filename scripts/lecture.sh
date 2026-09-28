#!/usr/bin/env bash
# lecture.sh — the deterministic part of the lecture → Markdown pipeline.
# The LLM steps (Q & A digest, topics notes) are described in skills/lecture-to-notes/SKILL.md.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"

usage() {
  cat <<'EOF'
Usage: lecture.sh <command> [options] VIDEO

Commands:
  probe       frame grabs to measure the slide area: probe.png (full) and check.png (cropped)
  audio       VIDEO → audio.wav (16 kHz mono)
  transcribe  audio.wav → transcript.txt  ("[start → end]  text" per line)
  proxy       cropped, downscaled, silent proxy.mp4 for scene detection
  scenes      proxy.mp4 → scenes.csv (PySceneDetect detect-adaptive)
  slides      scenes.csv + VIDEO → slides/NNNN_hhHmmMssS.png + slides/index.csv
  build       transcript.txt + slides/index.csv → lecture.md (Obsidian links)
  check       verify Obsidian links in the work directory's *.md files
  all         audio → transcribe → proxy → scenes → slides → build

Options:
  -o DIR     work directory (default: <video dir>/<video name without extension>)
  -c CROP    slide area as ffmpeg crop w:h:x:y, e.g. 1238:804:342:0 (default: full frame)
  -b BOX     black out a speaker overlay inside the cropped picture: x:y:w:h
  -e END     stop the proxy (and scene detection) here — where the slides end and Q & A starts.
             Seconds or hh:mm:ss. Default: whole video.
  -l LANG    whisper language code (default: uk)
  -p PROMPT  whisper initial prompt: a sentence in the lecture's language with the domain terms
  -m MODEL   whisper model (default: large-v3-turbo)
  -n MIN     minimal scene length for scenedetect (default: 3s)
  -d DIST    near-duplicate slide removal, imagehash distance (default: 6, 0 = off)
  -t TITLE   document title (default: video name)
  -T SEC     time of the probe frame (default: 600)
  -x ENC     proxy encoder: auto | videotoolbox | vaapi | x264 (default: auto)
  -f         overwrite existing outputs (default: skip steps whose output exists)

Environment: PYTHON, WHISPER_DEVICE (auto|cpu|cuda), WHISPER_COMPUTE (auto|int8|float16),
             VAAPI_DEVICE (default /dev/dri/renderD128)

Examples:
  lecture.sh probe -c 1238:804:342:0 lecture.mp4
  lecture.sh all -c 1238:804:342:0 -e 3:52:37 -p "Лекція про Harness, Claude Code, Codex, Pi" \
             -t "Harness Engineering, частина 1" lecture.mp4
EOF
}

die() { echo "lecture.sh: $*" >&2; exit 1; }
log() { printf '\n\033[1m== %s\033[0m\n' "$*" >&2; }

[[ $# -ge 1 ]] || { usage; exit 1; }
CMD="$1"; shift
[[ "$CMD" == -h || "$CMD" == --help || "$CMD" == help ]] && { usage; exit 0; }

WORK="" CROP="" BOX="" END="" LANG_="uk" PROMPT="" MODEL="large-v3-turbo" MINLEN="3s"
DEDUP=6 TITLE="" PROBE_T=600 ENC="auto" FORCE=0
while getopts ":o:c:b:e:l:p:m:n:d:t:T:x:fh" opt; do
  case $opt in
    o) WORK="$OPTARG" ;;   c) CROP="$OPTARG" ;;  b) BOX="$OPTARG" ;;    e) END="$OPTARG" ;;
    l) LANG_="$OPTARG" ;;  p) PROMPT="$OPTARG" ;; m) MODEL="$OPTARG" ;; n) MINLEN="$OPTARG" ;;
    d) DEDUP="$OPTARG" ;;  t) TITLE="$OPTARG" ;; T) PROBE_T="$OPTARG" ;; x) ENC="$OPTARG" ;;
    f) FORCE=1 ;;          h) usage; exit 0 ;;
    :) die "option -$OPTARG needs a value" ;;
    \?) die "unknown option -$OPTARG" ;;
  esac
done
shift $((OPTIND - 1))
[[ $# -eq 1 ]] || { usage; exit 1; }
VIDEO="$1"
[[ -f "$VIDEO" ]] || die "no such video: $VIDEO"

STEM="$(basename "${VIDEO%.*}")"
WORK="${WORK:-$(dirname "$VIDEO")/$STEM}"
TITLE="${TITLE:-$STEM}"
mkdir -p "$WORK"
VIDEO="$(cd "$(dirname "$VIDEO")" && pwd)/$(basename "$VIDEO")"
WORK="$(cd "$WORK" && pwd)"

# Skip a step when its output exists, unless -f.
fresh() { [[ $FORCE -eq 1 || ! -e "$1" ]] || { echo "skip: $1 exists (use -f to redo)" >&2; return 1; }; }

# crop + optional overlay box, as an ffmpeg filter prefix ("" or "crop=...,drawbox=...,")
crop_filter() {
  local f=""
  [[ -n "$CROP" ]] && f="crop=$CROP,"
  if [[ -n "$BOX" ]]; then
    local bx by bw bh
    IFS=: read -r bx by bw bh <<<"$BOX"
    f+="drawbox=x=$bx:y=$by:w=$bw:h=$bh:color=black:t=fill,"
  fi
  printf '%s' "$f"
}

pick_encoder() {
  [[ "$ENC" != auto ]] && return
  local encs; encs="$(ffmpeg -hide_banner -encoders 2>/dev/null || true)"
  if [[ "$(uname -s)" == Darwin ]] && grep -q h264_videotoolbox <<<"$encs"; then ENC=videotoolbox
  elif [[ -e "${VAAPI_DEVICE:-/dev/dri/renderD128}" ]] && grep -q h264_vaapi <<<"$encs"; then ENC=vaapi
  else ENC=x264; fi
}

step_probe() {
  log "probe"
  ffprobe -v error -select_streams v:0 -show_entries stream=width,height -show_entries format=duration \
    -of default=noprint_wrappers=1 "$VIDEO"
  ffmpeg -hide_banner -loglevel error -y -ss "$PROBE_T" -i "$VIDEO" -frames:v 1 "$WORK/probe.png"
  echo "full frame → $WORK/probe.png"
  local vf; vf="$(crop_filter)"
  if [[ -n "$vf" ]]; then
    ffmpeg -hide_banner -loglevel error -y -ss "$PROBE_T" -i "$VIDEO" -vf "${vf%,}" -frames:v 1 "$WORK/check.png"
    echo "cropped    → $WORK/check.png"
  fi
}

step_audio() {
  fresh "$WORK/audio.wav" || return 0
  log "audio"
  ffmpeg -hide_banner -loglevel warning -stats -y -i "$VIDEO" -vn -ac 1 -ar 16000 "$WORK/audio.wav"
}

step_transcribe() {
  fresh "$WORK/transcript.txt" || return 0
  [[ -f "$WORK/audio.wav" ]] || step_audio
  log "transcribe ($MODEL, $LANG_)"
  local args=("$WORK/audio.wav" -o "$WORK/transcript.txt" --model "$MODEL" --language "$LANG_")
  [[ -n "$PROMPT" ]] && args+=(--initial-prompt "$PROMPT")
  "$PY" "$HERE/transcribe.py" "${args[@]}"
}

step_proxy() {
  fresh "$WORK/proxy.mp4" || return 0
  pick_encoder
  log "proxy (encoder: $ENC)"
  local pre=() codec=() vf; vf="$(crop_filter)scale=640:-2"
  case $ENC in
    videotoolbox) codec=(-c:v h264_videotoolbox -b:v 1M) ;;
    vaapi) pre=(-vaapi_device "${VAAPI_DEVICE:-/dev/dri/renderD128}")
           vf+=",format=nv12,hwupload"; codec=(-c:v h264_vaapi -qp 30) ;;
    x264)  codec=(-c:v libx264 -preset veryfast -crf 30) ;;
    *) die "unknown encoder: $ENC" ;;
  esac
  local limit=(); [[ -n "$END" ]] && limit=(-t "$END")
  ffmpeg -hide_banner -loglevel warning -stats -y ${pre[@]+"${pre[@]}"} -i "$VIDEO" ${limit[@]+"${limit[@]}"} -an \
    -vf "$vf" "${codec[@]}" "$WORK/proxy.mp4"
  echo "proxy duration: $(ffprobe -v error -show_entries format=duration -of csv=p=0 "$WORK/proxy.mp4") s" >&2
}

step_scenes() {
  fresh "$WORK/scenes.csv" || return 0
  [[ -f "$WORK/proxy.mp4" ]] || step_proxy
  log "scenes (min $MINLEN)"
  (cd "$WORK" && scenedetect -i proxy.mp4 -m "$MINLEN" detect-adaptive list-scenes -f scenes.csv -q)
  echo "$(($(wc -l <"$WORK/scenes.csv") - 2)) scenes" >&2
}

step_slides() {
  fresh "$WORK/slides/index.csv" || return 0
  [[ -f "$WORK/scenes.csv" ]] || step_scenes
  log "slides"
  "$PY" "$HERE/extract_slides.py" "$VIDEO" "$WORK/scenes.csv" -o "$WORK/slides" \
    --crop "$CROP" --dedup "$DEDUP" --jobs "$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)"
}

step_build() {
  fresh "$WORK/lecture.md" || return 0
  [[ -f "$WORK/transcript.txt" ]] || step_transcribe
  [[ -f "$WORK/slides/index.csv" ]] || step_slides
  log "build"
  (cd "$WORK" && "$PY" "$HERE/build_lecture_md.py" transcript.txt slides/index.csv -o lecture.md \
    --title "$TITLE" --timestamps --obsidian)
}

step_check() {
  log "check links"
  shopt -s nullglob
  local files=("$WORK"/*.md)
  [[ ${#files[@]} -gt 0 ]] || die "no .md files in $WORK"
  "$PY" "$HERE/check_links.py" "${files[@]}"
}

case "$CMD" in
  probe) step_probe ;;  audio) step_audio ;;  transcribe) step_transcribe ;;
  proxy) step_proxy ;;  scenes) step_scenes ;; slides) step_slides ;;
  build) step_build ;;  check) step_check ;;
  all) step_audio; step_transcribe; step_proxy; step_scenes; step_slides; step_build ;;
  *) usage; die "unknown command: $CMD" ;;
esac
