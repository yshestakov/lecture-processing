#!/usr/bin/env python3
"""
Compact dump of a lecture file (output of build_lecture_md.py --obsidian) for reading by an LLM:

    === S12 00:20:36–00:26:10
    00:20:38 paragraph text ...

Only the slide sections are dumped; everything from the tail heading ("## Q & A") on is skipped
unless --with-tail. The dump is also split into chunks of about --chunk characters so an agent can
read it piece by piece (the line numbers where chunks start are printed to stderr).

Usage:
  dump_slides.py lecture.md -o /tmp/lecture_dump.txt
  dump_slides.py part2.md --chunk 20000 --with-tail
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SLIDE = re.compile(r"^## Slide (\d+)\s*$")
TIME = re.compile(r"^\*(\d\d:\d\d:\d\d)[–-](\d\d:\d\d:\d\d)\*\s*$")
PARA = re.compile(r"^`\[(\d\d:\d\d:\d\d)\]`\s*(.*)$")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lecture", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=None, help="output file (default: stdout)")
    ap.add_argument("--tail-title", default="Q & A")
    ap.add_argument("--with-tail", action="store_true", help="also dump the section after the slides")
    ap.add_argument("--chunk", type=int, default=20000, help="report chunk start lines every ~N characters")
    args = ap.parse_args()

    out: list[str] = []
    in_slide = False
    for line in args.lecture.read_text(encoding="utf-8").splitlines():
        if line.startswith("## ") and line[3:].strip() == args.tail_title and not args.with_tail:
            break
        m = SLIDE.match(line)
        if m:
            out.append(f"=== S{m.group(1)}")
            in_slide = True
            continue
        if line.startswith("## "):
            in_slide = False
            if args.with_tail:
                out.append(f"=== {line[3:].strip()}")
            continue
        if not in_slide and not args.with_tail:
            continue
        t = TIME.match(line)
        if t and out and out[-1].startswith("=== ") and " " not in out[-1][4:]:
            out[-1] += f" {t.group(1)}–{t.group(2)}"
            continue
        p = PARA.match(line)
        if p:
            out.append(f"{p.group(1)} {p.group(2)}")
        elif line.strip() and not line.startswith(("![", "*", "#")):
            out.append(line.strip())

    text = "\n".join(out) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)

    starts, size = [1], 0
    for i, line in enumerate(out, 1):
        size += len(line) + 1
        if size >= args.chunk:
            starts.append(i + 1)
            size = 0
    print(f"{len(text)} chars, {len(out)} lines; chunk start lines: {', '.join(map(str, starts))}", file=sys.stderr)


if __name__ == "__main__":
    main()
