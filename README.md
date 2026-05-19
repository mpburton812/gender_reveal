# Gender Reveal Media Extractor (archived)

> **This repository is archived and no longer maintained.**  
> **Active development:** [https://github.com/mpburton812/gender_reveal_media](https://github.com/mpburton812/gender_reveal_media)

See [ARCHIVED.md](ARCHIVED.md) for details on closure and where to contribute.

---

## Historical documentation

The following applied to this project before it was retired.

This script scraped transcripts from the Gender Reveal podcast website, extracted media references using Gemini AI, and synced them to a Turso database.

### Prerequisites

1. **Python 3.x**
2. **Gemini API Key**: Get a key from [Google AI Studio](https://aistudio.google.com/) and add `GEMINI_API_KEY` to `.env`.
3. **Turso Database**: Create a database at [Turso](https://turso.tech/) and add `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` to `.env`.

### Installation

```bash
pip install -r requirements.txt
```

### Usage

```bash
python extract_media.py
```

Options:

- `--limit N`: Limit processing to N episodes.
- `--backfill`: Re-process episodes even if they are already in the ledger.
- `--enrich`: Fetch missing cover art for existing records.
- `--sync-only`: Only run the database synchronization step.

### Media Explorer Dashboard

A Streamlit-based dashboard to explore and filter the extracted media data.

**Running locally**

1. Create `.streamlit/secrets.toml` with Turso credentials.
2. Run `streamlit run dashboard.py`.

Deployment and automation for this repo are no longer supported; use `gender_reveal_media` for current setup instructions.
