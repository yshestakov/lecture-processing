# Lecture notes vault — conventions

The vault (the folder that contains `process/`) holds recorded lectures turned into Obsidian notes, one subfolder per course. The pipeline is in `process/`:
`process/scripts/lecture.sh` does the deterministic part; the `lecture-to-notes` skill describes the LLM steps.

## Files per lecture

- `lecture.mp4` or the original video — never modify.
- `transcript.txt` (older lectures: `audio/output.txt`, `audio1.txt`): whisper segments `[start → end]  text`.
- `slides/` + `slides/index.csv` — slide images and their times.
- `lecture.md` / `partN.md` — full transcript mapped to slides. Headings `## Slide N`.
- `*.orig.md` — backup made before any merge. **Never overwrite or edit a `*.orig.md`.**
- `qa_digest*.md` — condensed Q & A, also merged into the lecture file.
- `*_topics.md` — topic notes (cleaned text + references), one per lecture file.

## Language and style

- Notes are written in **Ukrainian**, the language of the lectures. Technical terms stay in English (`harness`, `tool call`, `AGENTS.md`).
- Light cleanup only: remove filler, repetition and chat logistics; fix misrecognised terms. Don't add claims the speaker didn't make — corrections go into the references block.
- A name or number you could not verify is kept and marked *(за транскриптом)*.
- The course promotion is condensed to one short section. Personal or health details of speakers are summarised only in general terms.

## Obsidian links

- Heading links only: `[[#Heading|alias]]`, `[[lecture#Slide 12|12]]`. No HTML anchors, no `(#slug)` links.
- Inside tables, escape the alias pipe: `[[#1. Title\|Title]]`.
- Headings: unique; no `:` and none of `` ` * # | ^ [ ] ``. Put time ranges on an italic line under the heading: `*00:07:00–00:10:51 · Слайди [[lecture#Slide 2|2]]–[[lecture#Slide 9|9]]*`.
- Every link must resolve: run `python3 process/scripts/check_links.py <file>.md` and fix anything it reports before calling a note done.

## Working rules

- Transcripts are long (100–200K characters). Read them in ~20K-character chunks; don't load a whole file at once.
- Back up before changing a lecture file (`cp lecture.md lecture.orig.md` if no backup exists).
- References in «Додатково» blocks must be real pages you opened or found by search — no guessed URLs.
