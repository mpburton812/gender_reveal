# Project archived

**This repository is closed and read-only.** Development continues in the successor project:

**[https://github.com/mpburton812/gender_reveal_media](https://github.com/mpburton812/gender_reveal_media)**

## Why this repo was retired

This codebase was the original Gender Reveal podcast media extractor and Streamlit dashboard (Turso + Gemini + GitHub Actions). The project was superseded by `gender_reveal_media`, which is the active version for ongoing work and deployment.

## What was in this repo

| Area | Purpose |
|------|---------|
| `extract_media.py` | Scrape transcripts, extract media via Gemini, sync to Turso |
| `dashboard.py` | Streamlit media explorer |
| `export_to_csv.py` | CSV export utilities |
| `.github/workflows/extract.yml` | Daily automated pipeline (disabled before archive) |
| `versioning/` | Local development snapshots from May 2026 |

## Historical data

Committed pipeline artifacts (`extracted_media.csv`, `pipeline_state.json`, logs) remain in git history for reference. Do not open issues or pull requests here; use the new repository instead.

## Archive date

May 19, 2026
