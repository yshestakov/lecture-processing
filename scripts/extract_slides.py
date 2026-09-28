#!/usr/bin/env python3
"""
Extract one slide image per scene from a PySceneDetect `scenes.csv`.

Usage examples:
  python extract_slides.py lecture.mp4 scenes.csv
  python extract_slides.py lecture.mp4 scenes.csv --crop 1238:804:342:0 --pick end --dedup 6
  python extract_slides.py lecture.mp4 scenes.csv --format jpg --jobs 8

Output:
  slides/0001_00h00m00s.png ...   one image per scene
  slides/index.csv                scene number, file, start/end, frame time (for transcript alignment)
  slides/_dupes/                  near-duplicates moved here when --dedup is used
"""
import argparse
import csv
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def read_scenes(csv_path: Path):
    """Parse PySceneDetect list-scenes CSV (works with or without the 'Timecode List' first line)."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    for i, row in enumerate(rows):
        if row and row[0].strip() == "Scene Number":
            header = [c.strip() for c in row]
            break
    else:
        sys.exit(f"{csv_path}: header row with 'Scene Number' not found")

    scenes = []
    for row in rows[i + 1:]:
        if not row or not row[0].strip():
            continue
        r = dict(zip(header, row))
        scenes.append({
            "n": int(r["Scene Number"]),
            "start": float(r["Start Time (seconds)"]),
            "end": float(r["End Time (seconds)"]),
        })
    return scenes


def pick_time(start: float, end: float, mode: str, margin: float) -> float:
    """Choose the timestamp to grab inside a scene."""
    length = end - start
    if length <= 2 * margin:          # very short scene -> just take the middle
        return start + length / 2
    if mode == "start":
        return start + margin         # skip the fade-in of the transition
    if mode == "end":
        return end - margin           # fully built slide (all bullets/animations shown)
    return start + length / 2         # "middle"


def stamp(t: float) -> str:
    """Filesystem-safe timestamp: 01h23m45s."""
    t = int(t)
    return f"{t // 3600:02d}h{t % 3600 // 60:02d}m{t % 60:02d}s"


def grab_frame(video: Path, t: float, out: Path, vf: str | None, jpg_q: int):
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y",
           "-ss", f"{t:.3f}",          # input seek: fast, and frame-accurate in modern ffmpeg
           "-i", str(video)]
    if vf:
        cmd += ["-vf", vf]
    cmd += ["-frames:v", "1"]
    if out.suffix.lower() in (".jpg", ".jpeg"):
        cmd += ["-q:v", str(jpg_q)]   # 2 = best quality, 31 = worst
    cmd.append(str(out))
    subprocess.run(cmd, check=True)


def dedup(records, out_dir: Path, max_dist: int):
    """Move slides that look the same as the previous kept slide into _dupes/."""
    try:
        import imagehash
        from PIL import Image
    except ImportError:
        print("! --dedup needs: pip install imagehash pillow  (skipping dedup)")
        return records

    dupes_dir = out_dir / "_dupes"
    dupes_dir.mkdir(exist_ok=True)
    kept, prev_hash = [], None
    for rec in records:
        path = out_dir / rec["file"]
        h = imagehash.phash(Image.open(path))
        if prev_hash is not None and h - prev_hash <= max_dist:
            shutil.move(str(path), dupes_dir / rec["file"])
            kept[-1]["end"] = rec["end"]      # extend the previous slide's time range
            continue
        kept.append(rec)
        prev_hash = h
    print(f"dedup: kept {len(kept)} of {len(records)} slides "
          f"({len(records) - len(kept)} moved to {dupes_dir})")
    return kept


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("scenes_csv", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("slides"))
    ap.add_argument("--crop", default="1238:804:342:0",
                    help="ffmpeg crop w:h:x:y applied to saved slides ('' to disable)")
    ap.add_argument("--pick", choices=["start", "middle", "end"], default="end",
                    help="which moment of each scene to grab (default: end = fully built slide)")
    ap.add_argument("--margin", type=float, default=1.0,
                    help="seconds to stay away from scene boundaries (default 1.0)")
    ap.add_argument("--min-len", type=float, default=0.0,
                    help="skip scenes shorter than this many seconds")
    ap.add_argument("--format", choices=["png", "jpg"], default="png")
    ap.add_argument("--jpg-quality", type=int, default=2)
    ap.add_argument("--jobs", type=int, default=4, help="parallel ffmpeg processes")
    ap.add_argument("--dedup", type=int, default=0, metavar="DIST",
                    help="drop consecutive near-duplicates with pHash distance <= DIST (e.g. 6)")
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found in PATH")

    scenes = [s for s in read_scenes(args.scenes_csv) if s["end"] - s["start"] >= args.min_len]
    args.out.mkdir(parents=True, exist_ok=True)
    vf = f"crop={args.crop}" if args.crop else None

    records = []
    for s in scenes:
        t = pick_time(s["start"], s["end"], args.pick, args.margin)
        name = f"{s['n']:04d}_{stamp(s['start'])}.{args.format}"
        records.append({**s, "t": t, "file": name})

    print(f"extracting {len(records)} slides from {args.video} -> {args.out}/")
    failed = 0
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(grab_frame, args.video, r["t"], args.out / r["file"], vf, args.jpg_quality): r
                   for r in records}
        for i, fut in enumerate(as_completed(futures), 1):
            try:
                fut.result()
            except subprocess.CalledProcessError as e:
                failed += 1
                print(f"! scene {futures[fut]['n']} failed: {e}")
            if i % 50 == 0 or i == len(records):
                print(f"  {i}/{len(records)}")

    records = [r for r in records if (args.out / r["file"]).exists()]
    if args.dedup:
        records = dedup(records, args.out, args.dedup)

    with open(args.out / "index.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["slide", "scene", "file", "start_s", "end_s", "frame_s"])
        for i, r in enumerate(records, 1):
            w.writerow([i, r["n"], r["file"], f"{r['start']:.3f}", f"{r['end']:.3f}", f"{r['t']:.3f}"])

    print(f"done: {len(records)} slides, index at {args.out / 'index.csv'}"
          + (f", {failed} failed" if failed else ""))


if __name__ == "__main__":
    main()
