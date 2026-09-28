---
name: lecture-to-notes
description: Turn a recorded lecture video into Obsidian notes — slides, transcript mapped to slides, a Q & A digest and topic notes with references. Use for a new lecture video or to post-process an existing lecture.md / partN.md.
---

# Lecture → Obsidian notes

Two halves:

1. **Deterministic** — `scripts/lecture.sh`: ffmpeg, faster-whisper, PySceneDetect, slide extraction, transcript-to-slide mapping. Run it; don't reimplement it and don't read media files into context.
2. **Judgement** — Q & A digest and topic notes. That's your part.

Conventions (language, markers, Obsidian link rules) are in `AGENTS.md`. Follow them. Scripts live next to this skill in `process/scripts/` (in the container: `/opt/process/scripts`, already on `PATH`).

## Stage 1 — measure the video (ask the user to confirm)

```bash
lecture.sh probe -c W:H:X:Y VIDEO      # probe.png = full frame, check.png = cropped
```

- Look at `probe.png` and find the slide area (desktop share) and any speaker overlay. Propose a crop `w:h:x:y`, then check `check.png`.
- If the overlay sits inside the slide area, add `-b x:y:w:h` (coordinates in the cropped picture) to black it out.
- Ask the user where the slides end and the Q & A starts, if it's not obvious. This becomes `-e`.

## Stage 2 — run the pipeline

```bash
lecture.sh all -c 1238:804:342:0 -e 3:52:37 \
  -p "Лекція про <тему>: <English terms used in the talk>" \
  -t "<Course>, частина N" VIDEO
```

- Transcription of 4–5 h takes a long time on CPU. Run it in the background and check `transcript.txt` with `tail`.
- Sanity checks afterwards:
  - proxy duration matches `-e`;
  - the number of scenes is plausible (≈ one per minute or two for a talk);
  - `lecture.md` has a `## Q & A` tail if there was a Q & A.
- Steps skip existing outputs. Use `-f` to redo one.

## Stage 3 — Q & A digest (if the lecture has a Q & A tail)

1. Read the Q & A section in ~20K-character chunks.
2. Write `qa_digest.md` from `templates/qa_digest_template.md`:
   - a table of contents: #, time, topic link, keywords;
   - one `### N. Title` per question, with the question in 1–2 lines and the answer as bullets;
   - a `**Додатково:**` line with links where useful.
3. `cp lecture.md lecture.orig.md` (only if the backup doesn't exist).
4. Replace everything from `## Q & A` to the end of `lecture.md` with the digest: drop the title and demote headings one level.
5. Run `check_links.py lecture.md qa_digest.md`.

## Stage 4 — topic notes (`<file>_topics.md`)

1. `dump_slides.py lecture.md -o /tmp/dump.txt` writes the slides without the Q & A as `=== S<n> <start>–<end>` headers followed by the text, and prints the line numbers where ~20K-character chunks start. Read chunk by chunk (`sed -n 'a,bp'`), noting the time and slide range of every change of subject.
2. Group into 10–25 topics. Workshop/practice parts follow the steps of the practice. The course promotion becomes one short section. Questions asked inside the slides get their own numbered topic; the post-slide Q & A is linked, not redone.
3. Write the file from `templates/topics_template.md`:
   - header note: source, what was cleaned, and the *(за транскриптом)* marker;
   - contents table: #, time, topic link with `\|`, slides;
   - per topic:
     - `## N. Title`;
     - an italic line `*hh:mm:ss–hh:mm:ss · Слайди [[file#Slide a|a]]–[[file#Slide b|b]]*`;
     - cleaned bullets, tables where they help;
     - `#### Додатково` with 2–5 references.
4. **References.**
   - Search the web for each topic: official docs first, then the primary source (paper, blog post of the authors), then a good overview.
   - Open the page if unsure it exists. Never guess URLs.
   - Where the lecture is outdated or wrong, say so next to the link, with the correct figure.
   - Delegate this to a subagent if available, so fetched pages stay out of the main context.
5. Run `check_links.py <file>_topics.md`. Fix every broken link. Only then report done.

## Report

Tell the user:
- the file name and number of topics;
- the number of links, and that they all resolve;
- any corrections to the lecture's claims.

List the sources you used.
