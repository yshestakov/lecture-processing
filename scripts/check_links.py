#!/usr/bin/env python3
"""
Check that Obsidian wiki links in Markdown notes resolve.

  [[#Heading|alias]]        → heading in the same note
  [[note#Heading|alias]]    → heading in note.md (searched next to the checked file, then in --vault)
  [[note]]                  → note.md exists
  \\| inside tables is treated as the alias separator.
  [text](#anchor) links are reported too: Obsidian doesn't follow them.

Usage:
  check_links.py lecture_topics.md
  check_links.py Harness_Engineering/*.md --vault ~/Downloads/LLM

Exit code 1 if any link is broken (so an agent or a hook can gate on it).
"""
from __future__ import annotations

import argparse
import re
import sys
from functools import lru_cache
from pathlib import Path

LINK = re.compile(r"(?<!!)\[\[([^\]]+?)\]\]")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.M)
FENCE = re.compile(r"^```.*?^```", re.M | re.S)
ANCHOR = re.compile(r"\]\(#([^)]*)\)")  # [text](#anchor) — Obsidian can't follow these


def strip_code(text: str) -> str:
    text = FENCE.sub("", text)
    text = re.sub(r"``[^\n]*?``", "", text)
    return re.sub(r"`[^`\n]*`", "", text)


@lru_cache(maxsize=None)
def headings(path: Path) -> frozenset[str]:
    text = FENCE.sub("", path.read_text(encoding="utf-8"))
    return frozenset(h.strip() for h in HEADING.findall(text))


def find_note(name: str, base: Path, vault: Path | None) -> Path | None:
    cand = base / f"{name}.md"
    if cand.exists():
        return cand
    if vault:
        hits = sorted(vault.rglob(f"{Path(name).name}.md"))
        if hits:
            return hits[0]
    return None


def check(path: Path, vault: Path | None) -> tuple[int, int, list[str]]:
    text = strip_code(path.read_text(encoding="utf-8"))
    bad, n = [], 0
    for m in LINK.finditer(text):
        target = re.split(r"\\?\|", m.group(1), maxsplit=1)[0].strip()
        n += 1
        note, _, head = target.partition("#")
        if note:
            ref = find_note(note, path.parent, vault)
            if ref is None:
                bad.append(f"missing note: [[{target}]]")
                continue
        else:
            ref = path
        if head and head.strip() not in headings(ref):
            bad.append(f"missing heading in {ref.name}: [[{target}]]")
    anchors = [a.group(1) for a in ANCHOR.finditer(text)]
    if anchors:
        n += len(anchors)
        shown = ", ".join(f"#{a}" for a in anchors[:5]) + (", …" if len(anchors) > 5 else "")
        bad.append(f"{len(anchors)} HTML-style anchor links, Obsidian can't follow them ({shown}); "
                   f"use [[#Heading|text]]")
    nbad = len(bad) - (1 if anchors else 0) + len(anchors)
    return n, nbad, bad


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--vault", type=Path, default=None, help="vault root for notes not found next to the file")
    ap.add_argument("--include-orig", action="store_true", help="also check *.orig.md backups (skipped by default)")
    args = ap.parse_args()
    if not args.include_orig:
        args.files = [f for f in args.files if not f.name.endswith(".orig.md")]

    total_bad = 0
    for f in args.files:
        n, nbad, bad = check(f, args.vault)
        status = "OK" if not bad else f"{nbad} broken"
        print(f"{f}: {n} links, {status}")
        for b in bad:
            print(f"  {b}")
        total_bad += nbad
    sys.exit(1 if total_bad else 0)


if __name__ == "__main__":
    main()
