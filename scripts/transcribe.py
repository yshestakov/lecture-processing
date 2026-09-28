#!/usr/bin/env python3
"""
Transcribe an audio file with faster-whisper into the transcript format used by
build_lecture_md.py — one segment per line:

    [     0.0 →     22.6]  text ...

Segments are written as they are produced, so a long run can be watched with
`tail -f transcript.txt` and a partial file is still usable.

Usage:
  transcribe.py audio.wav -o transcript.txt --language uk \
      --initial-prompt "Лекція про Harness в агентах типу Codex, Claude Code, Pi"

Defaults follow what worked for 4–5 h Ukrainian lectures:
  large-v3-turbo, VAD on, condition_on_previous_text off (no drift or repetition loops).
Environment: WHISPER_DEVICE (auto|cpu|cuda), WHISPER_COMPUTE (auto|int8|float16|...).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("transcript.txt"))
    ap.add_argument("--model", default="large-v3-turbo",
                    help="whisper model; use large-v3 if you need --task translate")
    ap.add_argument("--language", default="uk", help="language code; set it explicitly (auto-detect confuses uk/ru)")
    ap.add_argument("--task", choices=["transcribe", "translate"], default="transcribe")
    ap.add_argument("--initial-prompt", default=None,
                    help="text in the lecture's language listing domain terms (keeps English terms in Latin script)")
    ap.add_argument("--beam-size", type=int, default=5)
    ap.add_argument("--no-vad", action="store_true", help="disable the VAD filter")
    ap.add_argument("--condition", action="store_true",
                    help="condition on previous text (off by default for long recordings)")
    ap.add_argument("--device", default=os.environ.get("WHISPER_DEVICE", "auto"))
    ap.add_argument("--compute-type", default=os.environ.get("WHISPER_COMPUTE", "auto"))
    ap.add_argument("--threads", type=int, default=0, help="CPU threads (0 = library default)")
    args = ap.parse_args()

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("faster-whisper is not installed: pip install faster-whisper")

    t0 = time.time()
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type,
                         cpu_threads=args.threads)
    segments, info = model.transcribe(
        str(args.audio),
        language=args.language,
        task=args.task,
        beam_size=args.beam_size,
        vad_filter=not args.no_vad,
        condition_on_previous_text=args.condition,
        initial_prompt=args.initial_prompt,
    )
    duration = info.duration or 0.0
    print(f"model={args.model} language={info.language} duration={duration / 60:.1f} min", file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with args.out.open("w", encoding="utf-8") as f:
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            f.write(f"[{seg.start:8.1f} → {seg.end:8.1f}]  {text}\n")
            f.flush()
            n += 1
            if n % 50 == 0 and duration:
                done = seg.end / duration
                el = time.time() - t0
                eta = el / done - el if done > 0 else 0
                print(f"  {done:6.1%}  {seg.end / 60:6.1f} min  elapsed {el / 60:5.1f} min  eta {eta / 60:5.1f} min",
                      file=sys.stderr)
    print(f"{n} segments → {args.out}  ({(time.time() - t0) / 60:.1f} min)", file=sys.stderr)


if __name__ == "__main__":
    main()
