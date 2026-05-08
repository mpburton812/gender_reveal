# Gender Reveal Media Explorer - Project Summary

## Overview
This project is an autonomous pipeline that scrapes transcripts from the *Gender Reveal* podcast, extracts media references (books, movies, music, etc.) using Gemini AI, enriches them with visual covers, and displays them in a high-end Streamlit dashboard.

## Key Features
1.  **AI-Powered Extraction**: Uses Gemini 2.5 Flash to identify media mentions and extract the specific "Why" context (the rationale behind the recommendation).
2.  **Visual Enrichment**: Automatically fetches book covers and movie posters using the Open Library and iTunes APIs.
3.  **Autonomous Pipeline**: Fully automated via GitHub Actions to run daily at midnight UTC. It processes 20 episodes per run until the entire 252-episode history is enriched.
4.  **Multi-View Dashboard**:
    *   **Episode Media References**: A searchable, chronological feed of every mention.
    *   **Visual Gallery**: A responsive grid layout of media cover art.
    *   **Most Mentioned Media**: A deduplicated list ranking items by their popularity in the community.
5.  **Direct Integration**: Includes one-click links to buy books on Bookshop.org, view movies on Letterboxd, and listen to the specific podcast episode.
6.  **Robust Logging & Notifications**: Generates performance and error logs for every run and sends a daily summary email to the administrator.

## System Architecture
*   **Language**: Python 3.10+
*   **AI**: Google Gemini Pro (with Search tool)
*   **Database**: Local CSV (`extracted_media.csv`) synchronized to Google Sheets.
*   **Hosting**: Dashboard on Streamlit Community Cloud; Pipeline on GitHub Actions.
*   **Security**: Credentials managed via `.env` (local) and GitHub Secrets (automated).

## Deployment & Maintenance
*   **Local Updates**: Run `python extract_media.py`.
*   **Manual Backfill**: Run `python extract_media.py --backfill --limit 20`.
*   **Automation**: Managed via `.github/workflows/extract.yml`.

---
*Created on Friday, May 8, 2026*
