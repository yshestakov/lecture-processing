#!/usr/bin/env python3
"""
Merge a faster-whisper transcript with extracted slides into one Markdown document.

Inputs:
  transcript  lines like  "[     0.0 →     22.6]  text ..."   (faster-whisper / whisper-ctranslate2 style)
  index.csv   produced by extract_slides.py (slide, scene, file, start_s, end_s, frame_s)

Each transcript segment is assigned to the slide that is on screen at the segment's midpoint.
A slide is considered on screen from its start until the next slide starts.

Usage:
  python build_lecture_md.py audio/output.txt slides/index.csv -o lecture.md --title "Harness Engineering, part 1"
  python build_lecture_md.py audio/output.txt slides/index.csv --timestamps      # [hh:mm:ss] before each paragraph
  python build_lecture_md.py audio/output.txt slides/index.csv --obsidian        # [[#Slide 2|…]] links for Obsidian
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

SEG_RE = re.compile(r"^\[\s*([\d.]+)\s*(?:→|->|-->)\s*([\d.]+)\s*\]\s*(.*)$")


def hms(t: float) -> str:
    t = int(t)
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"


def read_transcript(path: Path):
    segs = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            m = SEG_RE.match(line)
            if not m:
                print(f"! {path}:{n}: unrecognized line, skipped: {line[:60]}", file=sys.stderr)
                continue
            text = m.group(3).strip()
            if text:
                segs.append((float(m.group(1)), float(m.group(2)), text))
    return segs


def read_slides(path: Path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    slides = [{"n": int(r["slide"]), "file": r["file"],
               "start": float(r["start_s"]), "end": float(r["end_s"])} for r in rows]
    slides.sort(key=lambda s: s["start"])
    return slides


def obsidian_safe(title: str) -> str:
    """Heading text usable as an Obsidian link target: no : # | ^ [ ] ` *."""
    title = title.replace(":", " —")
    for ch in "#|^[]`*":
        title = title.replace(ch, "")
    return re.sub(r"\s+", " ", title).strip()


def link_text_safe(text: str) -> str:
    """Link labels must not close the link early."""
    return text.replace("[", "(").replace("]", ")").replace("|", "/")


def paragraphs(segs, pause: float, max_chars: int):
    """Group segments into paragraphs: break on a long pause or when a paragraph gets long."""
    paras, cur, cur_start, last_end, length = [], [], None, None, 0
    for start, end, text in segs:
        if cur and ((start - last_end) > pause or length > max_chars):
            paras.append((cur_start, " ".join(cur)))
            cur, length = [], 0
        if not cur:
            cur_start = start
        cur.append(text)
        length += len(text)
        last_end = end
    if cur:
        paras.append((cur_start, " ".join(cur)))
    return paras


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript", type=Path)
    ap.add_argument("index_csv", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("lecture.md"))
    ap.add_argument("--title", default=None, help="document title (default: output file name)")
    ap.add_argument("--slides-dir", type=Path, default=None,
                    help="folder with slide images (default: folder of index.csv)")
    ap.add_argument("--timestamps", action="store_true", help="prefix each paragraph with [hh:mm:ss]")
    ap.add_argument("--pause", type=float, default=2.0, help="pause (s) that starts a new paragraph")
    ap.add_argument("--max-chars", type=int, default=700, help="max paragraph length before breaking")
    ap.add_argument("--grace", type=float, default=30.0,
                    help="seconds after the last slide ends that still belong to it")
    ap.add_argument("--tail-title", default="Q & A",
                    help="heading for speech after the last slide (default: 'Q & A')")
    ap.add_argument("--tail-split", type=float, default=300.0,
                    help="split the after-slides section into sub-sections every N seconds (0 = no split)")
    ap.add_argument("--obsidian", action="store_true",
                    help="Obsidian-style links: [[#Heading|text]], no HTML anchors, times under headings")
    args = ap.parse_args()

    segs = read_transcript(args.transcript)
    slides = read_slides(args.index_csv)
    if not segs or not slides:
        sys.exit("empty transcript or slide index")

    slides_dir = args.slides_dir or args.index_csv.parent
    img_rel = os.path.relpath(slides_dir, args.out.parent.resolve() if args.out.parent != Path("") else Path.cwd())

    # Time window for each slide: [its start, next slide's start); last one ends at its own end (+ grace)
    for i, s in enumerate(slides):
        s["win_end"] = slides[i + 1]["start"] if i + 1 < len(slides) else s["end"] + args.grace
        s["segs"] = []
    tail = []   # speech after the last detected slide

    j = 0
    for seg in segs:
        mid = (seg[0] + seg[1]) / 2
        if mid >= slides[-1]["win_end"]:
            tail.append(seg)
            continue
        while j + 1 < len(slides) and mid >= slides[j]["win_end"]:
            j += 1
        # speech before the first slide goes to the first slide
        slides[j]["segs"].append(seg)

    title = args.title or args.out.stem
    total = segs[-1][1]
    lines = [f"# {title}", "",
             f"Duration {hms(total)} · {len(slides)} slides · transcript: `{args.transcript.name}`", "",
             "## Contents", ""]

    # --- link/heading style -------------------------------------------------
    # default : <a id="…"></a> anchor + "## Title · 00:07:00–00:10:51" + [text](#id)
    # obsidian: "## Title" + "*00:07:00–00:10:51*" line + [[#Title|text]]
    #           (no anchors; heading text is the link target, so it must not
    #            contain characters that break Obsidian heading links)
    def heading_name(anchor: str) -> str:
        if anchor == "no-slide":
            return obsidian_safe(args.tail_title)
        return f"Slide {anchor.split('-', 1)[1]}"

    def heading(level: int, anchor: str, when: str) -> list[str]:
        name = heading_name(anchor)
        if args.obsidian:
            return [f"{'#' * level} {name}", "", f"*{when}*", ""]
        return [f'<a id="{anchor}"></a>', f"{'#' * level} {name} · {when}", ""]

    def link(text: str, anchor: str) -> str:
        text = link_text_safe(text)
        if args.obsidian:
            return f"[[#{heading_name(anchor)}|{text}]]"
        return f"[{text}](#{anchor})"

    for s in slides:
        preview = (s["segs"][0][2][:70] + "…") if s["segs"] else "—"
        label = f"Slide {s['n']} · {hms(s['start'])}"
        lines.append(f"- {link(label, 'slide-' + str(s['n']))} — {preview}")
    if tail:
        lines.append(f"- {link(f'{args.tail_title} · {hms(tail[0][0])}', 'no-slide')}")
    lines += ["", "---", ""]

    def emit_text(seg_list):
        for t0, text in paragraphs(seg_list, args.pause, args.max_chars):
            lines.append(f"`[{hms(t0)}]` {text}" if args.timestamps else text)
            lines.append("")

    for s in slides:
        end = s["win_end"] if s is not slides[-1] else s["end"]
        lines += heading(2, f"slide-{s['n']}", f"{hms(s['start'])}–{hms(end)}")
        lines += [f"![Slide {s['n']}]({Path(img_rel, s['file']).as_posix()})", ""]
        if s["segs"]:
            emit_text(s["segs"])
        else:
            lines += ["*(no speech on this slide)*", ""]

    if tail:
        lines += heading(2, "no-slide", f"{hms(tail[0][0])}–{hms(tail[-1][1])}")
        if args.tail_split > 0:
            # sub-sections every N seconds so a long Q&A stays navigable
            chunk, chunk_start = [], tail[0][0]
            for seg in tail + [None]:
                if seg is None or (chunk and seg[0] - chunk_start >= args.tail_split):
                    lines += [f"### {hms(chunk[0][0])}", ""]
                    emit_text(chunk)
                    if seg is None:
                        break
                    chunk, chunk_start = [], seg[0]
                chunk.append(seg)
        else:
            emit_text(tail)

    args.out.write_text("\n".join(lines), encoding="utf-8")
    assigned = sum(len(s["segs"]) for s in slides)
    print(f"wrote {args.out}: {len(slides)} slides, {assigned} segments on slides"
          + (f", {len(tail)} segments after last slide ({hms(tail[0][0])}–{hms(tail[-1][1])})" if tail else ""))


if __name__ == "__main__":
    main()
