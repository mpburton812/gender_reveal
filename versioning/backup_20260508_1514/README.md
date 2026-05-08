# Gender Reveal Media Extractor

This script scrapes transcripts from the Gender Reveal podcast website, extracts media references using the Gemini AI, and syncs them to a Google Sheet.

## Prerequisites

1. **Python 3.x**
2. **Gemini API Key**: 
   - Get a free key from [Google AI Studio](https://aistudio.google.com/).
   - Paste the key into `extract_media.py` at `GEMINI_API_KEY`.
3. **Google Sheets Service Account**:
   - Go to the [Google Cloud Console](https://console.cloud.google.com/).
   - Create a new project.
   - Enable the **Google Sheets API** and **Google Drive API**.
   - Create a **Service Account** and download the JSON key file.
   - Rename the file to `service_account.json` and place it in this directory.
   - **Important**: Open your Google Sheet and "Share" it with the email address found in your `service_account.json` (e.g., `your-service-account@project-id.iam.gserviceaccount.com`) as an Editor.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

## Media Explorer Dashboard

A Streamlit-based dashboard to explore and filter the extracted media data.

### Running Locally

```bash
streamlit run dashboard.py
```

### Deployment

To deploy to **Streamlit Community Cloud**:
1. Push this project to a public GitHub repository.
2. Connect your GitHub account to [Streamlit Cloud](https://share.streamlit.io/).
3. Select this repository and `dashboard.py` as the main file.
