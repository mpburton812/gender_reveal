# Gender Reveal Media Extractor

This script scrapes transcripts from the Gender Reveal podcast website, extracts media references using the Gemini AI, and syncs them to a Turso database.

## Prerequisites

1. **Python 3.x**
2. **Gemini API Key**: 
   - Get a free key from [Google AI Studio](https://aistudio.google.com/).
   - Add it to your `.env` file as `GEMINI_API_KEY`.
3. **Turso Database**:
   - Create a database at [Turso](https://turso.tech/).
   - Obtain your **Database URL** and **Auth Token**.
   - Add them to your `.env` file as `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python extract_media.py
```

Options:
- `--limit N`: Limit processing to N episodes.
- `--backfill`: Re-process episodes even if they are already in the ledger.
- `--enrich`: Fetch missing cover art for existing records.
- `--sync-only`: Only run the database synchronization step.

## Media Explorer Dashboard

A Streamlit-based dashboard to explore and filter the extracted media data.

### Running Locally

1. Create a `.streamlit/secrets.toml` file with your Turso credentials:
   ```toml
   [turso]
   url = "libsql://..."
   auth_token = "..."
   ```
2. Run the dashboard:
   ```bash
   streamlit run dashboard.py
   ```

### Deployment

To deploy to **Streamlit Community Cloud**:
1. Push this project to a public GitHub repository.
2. Connect your GitHub account to [Streamlit Cloud](https://share.streamlit.io/).
3. Select this repository and `dashboard.py` as the main file.
4. Add your secrets (`GEMINI_API_KEY`, `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, and the `[turso]` section) in the Streamlit Cloud dashboard.
