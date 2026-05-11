import os
import json
import time
import csv
import re
import io
import requests
import traceback
import argparse
import logging
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
import libsql_client
from typing import List, Dict, Any
import docx
import PyPDF2
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(override=True)

# --- CONFIGURATION ---
URL_LISTEN = "https://www.genderpodcast.com/listen"
TRANSCRIPTS_DIR = "transcripts"
PIPELINE_STATE_FILE = "pipeline_state.json"
CSV_OUTPUT = "extracted_media.csv"

# Turso Database Configuration
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

# Logging Configuration
ERROR_LOG = "error_log.txt"
PERFORMANCE_LOG = "performance_log.txt"

# Gemini API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL_NAME = "gemini-2.5-flash" # Current standard for 2026

# ... (rest of configuration unchanged)

# --- LOGGING SETUP ---

def setup_logging():
    """Configures separate loggers for errors and performance tracking."""
    # Error Logger (For technical failures and stack traces)
    error_logger = logging.getLogger('error_logger')
    error_logger.setLevel(logging.ERROR)
    if not error_logger.handlers:
        error_handler = logging.FileHandler(ERROR_LOG, encoding='utf-8')
        error_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        error_logger.addHandler(error_handler)

    # Performance Logger (For execution summaries and step-by-step progress)
    perf_logger = logging.getLogger('perf_logger')
    perf_logger.setLevel(logging.INFO)
    if not perf_logger.handlers:
        perf_handler = logging.FileHandler(PERFORMANCE_LOG, encoding='utf-8')
        perf_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        perf_logger.addHandler(perf_handler)
    
    return error_logger, perf_logger

error_log, perf_log = setup_logging()

class ExecutionSummary:
    """Tracks metrics for the performance log."""
    def __init__(self):
        self.start_time = datetime.now()
        self.episodes_found = 0
        self.episodes_processed = 0
        self.episodes_skipped = 0
        self.media_refs_extracted = 0
        self.errors_encountered = 0
        self.sync_success = False

    def log_summary(self, perf_logger):
        duration = datetime.now() - self.start_time
        summary = (
            f"\n--- EXECUTION SUMMARY ---\n"
            f"Run Date: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Duration: {duration}\n"
            f"Episodes Found: {self.episodes_found}\n"
            f"Episodes Processed (AI): {self.episodes_processed}\n"
            f"Episodes Skipped (Already Done): {self.episodes_skipped}\n"
            f"Total Media Refs Extracted: {self.media_refs_extracted}\n"
            f"Errors Encountered: {self.errors_encountered}\n"
            f"Turso Database Sync: {'SUCCESS' if self.sync_success else 'FAILED/SKIPPED'}\n"
            f"---------------------------\n"
        )
        perf_logger.info(summary)
        print(summary)

# --- UTILS ---

# Conservative Rate Limiting (Lowered for stability)
# Flash Free Tier is officially 15 RPM/1M TPM, but we'll use 5/500k for safety with Search.
TPM_LIMIT = 500000
RPM_LIMIT = 5 

# Media Categories
CATEGORIES = [
    "academic", "artists", "books", "games", "graphic novels",
    "movies", "music", "podcasts", "publications", "tv shows",
    "websites", "zines"
]

# --- UTILS ---

def get_headers():
    """Browser-like headers to avoid being blocked by Squarespace."""
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

class RSSDataFetcher:
    """Fetches and maps episode dates and show notes from the Libsyn RSS feed."""
    RSS_URL = "https://gender.libsyn.com/rss"

    def __init__(self):
        self.episode_map = {} # Map of ep_key -> {date, show_notes}
        self._fetch_rss_data()

    def _fetch_rss_data(self):
        print(f"Fetching episode data from {self.RSS_URL}...")
        try:
            response = retry_with_backoff(lambda: requests.get(self.RSS_URL, timeout=30))
            soup = BeautifulSoup(response.content, 'xml')
            items = soup.find_all('item')
            
            for item in items:
                title = item.title.text if item.title else ""
                pub_date_raw = item.pubDate.text if item.pubDate else ""
                link = item.link.text if item.link else ""
                # Use description or content:encoded for show notes
                show_notes = item.description.text if item.description else ""
                if not show_notes and item.find('content:encoded'):
                    show_notes = item.find('content:encoded').text
                
                # Format: Mon, 27 Apr 2026 07:00:00 +0000 -> 27 Apr 2026
                date_match = re.search(r'\d{1,2}\s+[A-Za-z]{3}\s+\d{4}', pub_date_raw)
                pub_date = date_match.group(0) if date_match else pub_date_raw

                data = {"date": pub_date, "show_notes": show_notes, "link": link}

                # Try to extract episode number
                num_match = re.search(r'(?:Episode|Epsiode)\s*(\d+\.?\d*)', title, re.IGNORECASE)
                if num_match:
                    self.episode_map[num_match.group(1)] = data
                
                # Also store by cleaned title for bonus episodes
                clean_title = clean_guest_name(title)
                if clean_title:
                    self.episode_map[clean_title.lower()] = data
                    
        except Exception as e:
            print(f"WARNING: Could not fetch RSS data: {e}")

    def get_data(self, ep_num: str, ep_name: str) -> Dict:
        # Try by number first
        if ep_num and ep_num in self.episode_map:
            return self.episode_map[ep_num]
        
        # Try by cleaned name
        clean_name = clean_guest_name(ep_name).lower()
        if clean_name in self.episode_map:
            return self.episode_map[clean_name]
            
        return {"date": "", "show_notes": ""}

class TokenRateLimiter:
    """Tracks and manages TPM (Tokens Per Minute) and RPM (Requests Per Minute) limits."""
    def __init__(self, tpm_limit: int, rpm_limit: int):
        self.tpm_limit = tpm_limit
        self.rpm_limit = rpm_limit
        self.tokens_used = [] # List of (timestamp, token_count)
        self.requests_made = [] # List of timestamps

    def _clean_old_records(self):
        now = time.time()
        self.tokens_used = [r for r in self.tokens_used if now - r[0] < 60]
        self.requests_made = [t for t in self.requests_made if now - t < 60]

    def wait_for_capacity(self, estimated_tokens: int):
        """Blocks until there is capacity for the estimated tokens and a new request."""
        # Safeguard against tokens exceeding limit
        if estimated_tokens > self.tpm_limit:
            estimated_tokens = self.tpm_limit

        while True:
            self._clean_old_records()
            current_tpm = sum(r[1] for r in self.tokens_used)
            current_rpm = len(self.requests_made)

            if current_rpm < self.rpm_limit and (current_tpm + estimated_tokens) <= self.tpm_limit:
                break
            
            # Calculate sleep time
            sleep_time = 1
            if current_rpm >= self.rpm_limit:
                # Wait until the oldest request is > 60s old
                sleep_time = max(sleep_time, 60 - (time.time() - self.requests_made[0]) + 0.5)
            
            if (current_tpm + estimated_tokens) > self.tpm_limit:
                # Find how many tokens we need to drop
                needed = (current_tpm + estimated_tokens) - self.tpm_limit
                dropped = 0
                for ts, count in self.tokens_used:
                    dropped += count
                    if dropped >= needed:
                        sleep_time = max(sleep_time, 60 - (time.time() - ts) + 0.5)
                        break
            
            print(f"      GEMINI RATE LIMIT: Waiting {sleep_time:.1f}s for capacity (Current TPM: {current_tpm}, RPM: {current_rpm})...")
            time.sleep(sleep_time)

    def record_usage(self, token_count: int):
        """Records actual token usage after a successful request."""
        now = time.time()
        self.tokens_used.append((now, token_count))
        self.requests_made.append(now)

def retry_with_backoff(fn, max_retries=5, initial_delay=2, cap=60):
    """Exponential backoff wrapper for API calls and web requests."""
    attempt = 0
    while attempt < max_retries:
        try:
            return fn()
        except Exception as e:
            err_msg = str(e).lower()
            
            # Identify the type of error for a cleaner message
            source = "GENERIC"
            # Check if it's a requests error with a response
            if hasattr(e, 'response') and e.response is not None:
                source = f"WEBSITE ({e.response.url})"
            # Check if it's a Gemini/Google error
            elif "genai" in str(type(e)).lower() or "google" in err_msg or "resource_exhausted" in err_msg:
                source = "GEMINI API"

            if "503" in err_msg or "unavailable" in err_msg:
                friendly_err = f"{source}: Server temporarily unavailable (503)"
            elif "429" in err_msg or "rate limit" in err_msg or "quota" in err_msg or "exhausted" in err_msg:
                friendly_err = f"{source}: Rate limit or quota exceeded (429)"
            elif "500" in err_msg:
                friendly_err = f"{source}: Internal server error (500)"
            else:
                friendly_err = f"{source}: Unexpected error: {e}"

            if any(code in err_msg for code in ["429", "503", "500", "rate limit", "unavailable", "quota", "exhausted"]):
                delay = min(initial_delay * (2 ** attempt), cap)
                print(f"      {friendly_err}. Retrying in {delay}s (Attempt {attempt + 1}/{max_retries})...")
                time.sleep(delay)
                attempt += 1
            else:
                raise e
    raise Exception(f"Max retries exceeded for function {fn.__name__}")

def clean_guest_name(name: str) -> str:
    """Removes common prefixes and noise from guest/episode names."""
    # Remove "Bonus: "
    name = re.sub(r'^Bonus:\s*', '', name, flags=re.IGNORECASE)
    # Remove "Checking in with "
    name = re.sub(r'^Checking\s+in\s+with\s+', '', name, flags=re.IGNORECASE)
    # Remove "Spicy Advicey with "
    name = re.sub(r'^Spicy\s+Advicey\s+with\s+', '', name, flags=re.IGNORECASE)
    # Remove "Advice Questions with "
    name = re.sub(r'^\d+\s+Advice\s+Questions\s+with\s+', '', name, flags=re.IGNORECASE)
    # Remove "Live in/at ..."
    name = re.sub(r'^Live\s+(?:in|at)\s+[^:]+[:\s]*', '', name, flags=re.IGNORECASE)
    # Remove "Speed Reading"
    name = re.sub(r'^SPEED\s+READING\s*', '', name, flags=re.IGNORECASE)
    
    # Trim common suffix noise
    name = re.sub(r'\(Live\)', '', name, flags=re.IGNORECASE)
    name = re.sub(r'segment transcript', '', name, flags=re.IGNORECASE)
    name = re.sub(r'’s villain era', '', name, flags=re.IGNORECASE)
    
    return name.strip()

# --- SCRAPER ---

class GenderRevealScraper:
    def __init__(self, transcripts_dir: str):
        self.transcripts_dir = transcripts_dir
        if not os.path.exists(transcripts_dir):
            os.makedirs(transcripts_dir)

    def scrape_episodes(self):
        print(f"Scraping {URL_LISTEN}...")
        response = retry_with_backoff(lambda: requests.get(URL_LISTEN, headers=get_headers(), timeout=30))
        soup = BeautifulSoup(response.content, 'html.parser')
        
        episodes_data = []
        current_season = None
        
        # Squarespace content area
        content_div = soup.find('div', class_='sqs-layout') or soup.find('main')
        if not content_div:
            print("WARNING: Could not find main content area on page.")
            return []
        
        # Find all season headers and lists
        elements = content_div.find_all(['h2', 'ul', 'p'])
        
        for i, element in enumerate(elements):
            text = element.get_text(strip=True)
            
            # Detect Season headers (e.g., "Season 14" or "Season 7")
            if "SEASON" in text.upper() and len(text) < 20:
                current_season = text.strip()
                continue
                
            # If it's a list (ul), it might contain episodes with embedded transcript links
            if element.name == 'ul':
                for li in element.find_all('li'):
                    li_text = li.get_text()
                    
                    # Pattern 1: Episode 188: Whit Washington
                    match = re.search(r'(?:Episode|Epsiode)\s*(\d+\.?\d*):?\s*(.*)', li_text, re.IGNORECASE)
                    
                    # Pattern 2: Bonus: ...
                    bonus_match = re.search(r'Bonus:\s*(.*)', li_text, re.IGNORECASE)
                    
                    if match or bonus_match:
                        if match:
                            ep_num = match.group(1)
                            ep_name = match.group(2).split('(')[0].strip()
                        else:
                            ep_num = "Bonus"
                            ep_name = bonus_match.group(1).split('(')[0].strip()
                        
                        # Find link within this <li>
                        link_el = li.find('a')
                        if link_el:
                            url = link_el.get('href')
                            if url and ("/s/" in url or "/transcripts/" in url or "transcript" in url.lower()):
                                if url.startswith('/'):
                                    url = "https://www.genderpodcast.com" + url
                                
                                episodes_data.append({
                                    "season": current_season,
                                    "episode_number": ep_num,
                                    "episode_name": ep_name,
                                    "transcript_url": url
                                })
                                continue # Found transcript in the link title itself

                    # Check for "transcript" link specifically if not found above
                    transcript_links = li.find_all('a')
                    for tl in transcript_links:
                        if "transcript" in tl.get_text().lower():
                            url = tl.get('href')
                            if url:
                                if url.startswith('/'):
                                    url = "https://www.genderpodcast.com" + url
                                episodes_data.append({
                                    "season": current_season,
                                    "episode_number": ep_num if 'ep_num' in locals() else "Unknown",
                                    "episode_name": ep_name if 'ep_name' in locals() else li_text,
                                    "transcript_url": url
                                })

        return episodes_data

    def download_transcript(self, url: str, filename: str):
        # Determine extension based on URL if not in filename
        ext = url.split('.')[-1].lower()
        if ext not in ['txt', 'docx', 'pdf', 'doc', 'odt']:
            ext = 'html'
        
        # Ensure filename has correct extension
        base_name = os.path.splitext(filename)[0]
        full_filename = f"{base_name}.{ext}"
        path = os.path.join(self.transcripts_dir, full_filename)
        
        if os.path.exists(path):
            return full_filename
            
        print(f"Downloading transcript: {url} -> {full_filename}")
        def fetch():
            res = requests.get(url, timeout=30, headers=get_headers())
            res.raise_for_status()
            return res.content

        try:
            # Politeness delay to avoid website rate limits
            time.sleep(2)
            content = retry_with_backoff(fetch)
            with open(path, 'wb') as f:
                f.write(content)
            return full_filename
        except Exception as e:
            print(f"      FAILED to download {url}: {e}")
            return None

    def extract_text(self, filename: str):
        path = os.path.join(self.transcripts_dir, filename)
        ext = filename.split('.')[-1].lower()
        
        try:
            if ext == 'docx':
                doc = docx.Document(path)
                return "\n".join([para.text for para in doc.paragraphs])
            elif ext == 'pdf':
                reader = PyPDF2.PdfReader(path)
                text = ""
                for page in reader.pages:
                    text += page.extract_text()
                return text
            elif ext in ['txt', 'html']:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                if ext == 'html':
                    soup = BeautifulSoup(content, 'html.parser')
                    # Look for main content or transcript area
                    body = soup.find('div', class_='sqs-layout') or \
                           soup.find('main') or \
                           soup.find('article') or \
                           soup.find('div', class_='entry-content')
                    return body.get_text(separator='\n') if body else soup.get_text()
                return content
            elif ext in ['doc', 'odt']:
                print(f"      WARNING: Binary format .{ext} not directly supported. Skipping.")
                return ""
            else:
                # Try reading as text as fallback for unknown extensions
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    return f.read()
        except Exception as e:
            print(f"Error reading file {filename}: {e}")
            return ""

# --- EXTRACTION ---

class MediaExtractor:
    def __init__(self, api_key: str, tpm_limit: int, rpm_limit: int):
        self.client = genai.Client(api_key=api_key)
        self.rate_limiter = TokenRateLimiter(tpm_limit, rpm_limit)

    def extract_from_text(self, text: str, ep_metadata: Dict, show_notes: str = "") -> List[Dict]:
        prompt = f"""
Review the following podcast transcript and show notes to extract all media references.
Media references are books, movies, music, etc., that the host or guest mentions.

FOR EACH MEDIA ITEM FOUND:
1. DO NOT extract "Gender Reveal" (the podcast itself) or references to specific Gender Reveal episodes or segments.
2. For ALL other media items, use your search tool to LOOK UP a canonical URL for the work (e.g., its Wikipedia page, IMDb page, or official website). DO NOT use the URLs provided in the transcript or show notes for these items.

Return ONLY a JSON array of objects. Each object MUST use these exact keys:
- "media_type": Must be one of {', '.join(CATEGORIES)}. (MUST BE PLURAL).
- "media_sub_category": (e.g., "Graphic Memoir" for a Graphic Novel, or "Indie Folk" for Music).
- "media_name": The title or name of the work.
- "url_to_media": The canonical URL you found via search.
- "guest": The guest for this episode ({ep_metadata.get('guest', 'Unknown')}).
- "mention_context": A 1-2 sentence snippet from the transcript explaining WHY this media was mentioned or what was said about it.

Episode Metadata: Season {ep_metadata.get('season')}, Episode {ep_metadata.get('episode_number')}, Name "{ep_metadata.get('episode_name')}".

Show Notes (For context):
{show_notes}

Transcript Text:
{text[:100000]}
"""
        # ... (token estimation and Gemini call logic unchanged)
        # Estimate tokens (approx 3 chars per token + safety margin for output)
        estimated_tokens = (len(prompt) // 3) + 2000
        self.rate_limiter.wait_for_capacity(estimated_tokens)

        def call_gemini():
            response = self.client.models.generate_content(
                model=GEMINI_MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            )
            
            # Record actual usage
            try:
                tokens = response.usage_metadata.total_token_count
                self.rate_limiter.record_usage(tokens)
            except:
                self.rate_limiter.record_usage(estimated_tokens)

            raw_text = response.text
            if not raw_text:
                print("      WARNING: Gemini returned an empty response. This might be due to safety filters or a model error.")
                return []

            # Try to find and parse a JSON array
            json_match = re.search(r'\[.*\]', raw_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    print(f"      DEBUG: Found JSON-like block but failed to parse: {raw_text[:200]}...")
            
            # Final attempt at parsing the whole response
            try:
                return json.loads(raw_text)
            except json.JSONDecodeError:
                # If it's not JSON, it might be a text refusal or error message
                print(f"      ERROR: AI response was not valid JSON. First 200 chars: {raw_text[:200]}")
                return []

        results = retry_with_backoff(call_gemini)
        
        # Mapping to handle potential casing/space variations from AI
        key_map = {
            "Media Type": "media_type",
            "type": "media_type",
            "Media Sub-category": "media_sub_category",
            "sub_category": "media_sub_category",
            "subcategory": "media_sub_category",
            "Media Name": "media_name",
            "name": "media_name",
            "title": "media_name",
            "URL to media": "url_to_media",
            "url": "url_to_media",
            "link": "url_to_media",
            "Guest": "guest",
            "Date": "media_date",
            "media_date": "media_date",
            "release_date": "media_date"
        }

        # Enrich and normalize results
        final_results = []
        for item in (results or []):
            if not isinstance(item, dict):
                continue

            normalized_item = {}
            # Apply mapping and lowercase keys
            for k, v in item.items():
                new_key = key_map.get(k, k.lower().replace(" ", "_"))
                normalized_item[new_key] = v

            # --- REFINEMENT LOGIC ---
            m_name = str(normalized_item.get('media_name', '')).lower()
            m_type = str(normalized_item.get('media_type', '')).lower()

            # 1. Filter out "Gender Reveal" self-references
            if "gender reveal" in m_name:
                continue

            # 2. Map "youtube channels" to "websites"
            if "youtube" in m_type or "youtube" in m_name:
                normalized_item['media_type'] = "websites"
                m_type = "websites"

            # 3. Filter out undesired categories
            if m_type in ["franchises", "organizations"]:
                continue
            
            # Normalize category values (existing logic)
            if normalized_item.get('media_type') == 'academics':
                normalized_item['media_type'] = 'academic'
            if normalized_item.get('media_type') == 'tv_shows':
                normalized_item['media_type'] = 'tv shows'

            # Ensure episode metadata is present
            normalized_item['season'] = ep_metadata.get('season')
            normalized_item['episode_number'] = ep_metadata.get('episode_number')
            normalized_item['episode_name'] = ep_metadata.get('episode_name')
            normalized_item['episode_date'] = ep_metadata.get('episode_date')
            normalized_item['episode_url'] = ep_metadata.get('episode_url')
            
            # Ensure all expected fields exist
            for header in ["media_date", "guest", "media_type", "media_sub_category", "media_name", "url_to_media", "mention_context", "image_url", "episode_url"]:
                if header not in normalized_item:
                    normalized_item[header] = None

            # Only add if it has at least a media name
            if normalized_item.get('media_name'):
                final_results.append(normalized_item)
            
        return final_results

# --- ENRICHMENT (Cover Art) ---

class MediaEnricher:
    """Fetches cover art and posters from various free APIs."""
    
    def fetch_image(self, media_name: str, media_type: str) -> str:
        """Determines which API to use based on media type."""
        if not media_name or media_name.lower() == "unknown":
            return None
            
        m_type = media_type.lower()
        if 'book' in m_type or 'graphic novel' in m_type:
            return self._fetch_book_cover(media_name)
        elif 'podcast' in m_type or 'music' in m_type:
            return self._fetch_itunes_art(media_name)
        elif 'movie' in m_type or 'tv show' in m_type:
            return self._fetch_itunes_art(media_name, entity='movie' if 'movie' in m_type else 'tvShow')
        return None

    def _fetch_book_cover(self, title: str) -> str:
        """Uses Open Library Search API to find a book cover."""
        try:
            # Open Library is very rate-limited, so we use a small delay
            time.sleep(0.5)
            url = f"https://openlibrary.org/search.json?title={requests.utils.quote(title)}&limit=1"
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get('docs'):
                    cover_i = data['docs'][0].get('cover_i')
                    if cover_i:
                        return f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg"
        except:
            pass
        return None

    def _fetch_itunes_art(self, name: str, entity='podcast') -> str:
        """Uses iTunes Search API for podcasts, music, and movies."""
        try:
            url = f"https://itunes.apple.com/search?term={requests.utils.quote(name)}&entity={entity}&limit=1"
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get('results'):
                    # Use a larger version of the artwork (600x600 instead of 100x100)
                    art_url = data['results'][0].get('artworkUrl100')
                    if art_url:
                        return art_url.replace('100x100bb', '600x600bb')
        except:
            pass
        return None

# --- STATE MANAGEMENT ---

class PipelineState:
    def __init__(self, state_file: str, csv_file: str):
        self.state_file = state_file
        self.csv_file = csv_file
        self.state = self.load_state()

    def load_state(self):
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r') as f:
                return json.load(f)
        return {"processed_files_ledger": []}

    def save_state(self):
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=4)

    def is_processed(self, filename):
        return filename in self.state["processed_files_ledger"]

    def mark_processed(self, filename):
        if filename not in self.state["processed_files_ledger"]:
            self.state["processed_files_ledger"].append(filename)
            self.save_state()

    def remove_episode_from_csv(self, episode_number):
        """Removes all rows for a specific episode number to prepare for a backfill."""
        if not os.path.exists(self.csv_file):
            return
        
        try:
            # Function to extract numeric part for robust comparison
            def to_float(val):
                try:
                    match = re.search(r'(\d+)', str(val))
                    return float(match.group(1)) if match else -1.0
                except: return -1.0

            df = pd.read_csv(self.csv_file)
            target_num = to_float(episode_number)
            
            initial_count = len(df)
            # Remove rows where the numeric part of episode_number matches
            df = df[df['episode_number'].apply(to_float) != target_num]
            
            if len(df) < initial_count:
                df.to_csv(self.csv_file, index=False)
                print(f"      CLEANUP: Removed {initial_count - len(df)} old entries for Episode {episode_number}")
        except Exception as e:
            print(f"      WARNING: Could not clean CSV for backfill: {e}")

    def append_to_csv(self, data: List[Dict]):
        file_exists = os.path.isfile(self.csv_file)
        headers = [
            "season", "episode_number", "episode_name", "episode_date", "guest",
            "media_type", "media_sub_category", "media_name", "url_to_media", 
            "mention_context", "image_url", "episode_url"
        ]
        with open(self.csv_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
            if not file_exists:
                writer.writeheader()
            writer.writerows(data)


def sort_dataframe(df):
    """Sorts the dataframe by Season and Episode number numerically."""
    def extract_num(val):
        if pd.isna(val) or val == "": return 0
        match = re.search(r'(\d+)', str(val))
        if match: return float(match.group(1))
        # Handle "Bonus" episodes by placing them at the end of the season
        if "bonus" in str(val).lower(): return 999.0 
        return 0

    df['season_sort'] = df['season'].apply(extract_num)
    df['ep_sort'] = df['episode_number'].apply(extract_num)
    
    # Sort and then drop the helper columns
    df = df.sort_values(by=['season_sort', 'ep_sort'], ascending=[True, True])
    df = df.drop(columns=['season_sort', 'ep_sort'])
    return df

# --- TURSO DATABASE ---

def sync_to_turso(csv_file):
    if not TURSO_DATABASE_URL or not TURSO_AUTH_TOKEN:
        print("Skipping Turso sync: TURSO_DATABASE_URL or TURSO_AUTH_TOKEN not found in environment.")
        return False

    if not os.path.exists(csv_file) or os.stat(csv_file).st_size == 0:
        print("Skipping Turso sync: CSV file is empty or missing.")
        return False

    print(f"Syncing to Turso Database ({TURSO_DATABASE_URL})...")
    
    try:
        df = pd.read_csv(csv_file, encoding='utf-8')
    except Exception:
        df = pd.read_csv(csv_file, encoding='utf-8', on_bad_lines='skip')
    
    df = df.fillna("")
    if df.empty:
        print("CSV is empty, nothing to sync.")
        return False

    # Sort before syncing
    df = sort_dataframe(df)
    df.to_csv(csv_file, index=False)

    try:
        # libsql-client sync execute
        client = libsql_client.create_client_sync(url=TURSO_DATABASE_URL, auth_token=TURSO_AUTH_TOKEN)
        
        # Create table if not exists
        client.execute("""
            CREATE TABLE IF NOT EXISTS media_references (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season TEXT,
                episode_number TEXT,
                episode_name TEXT,
                episode_date TEXT,
                guest TEXT,
                media_type TEXT,
                media_sub_category TEXT,
                media_name TEXT,
                url_to_media TEXT,
                mention_context TEXT,
                image_url TEXT,
                episode_url TEXT
            )
        """)
        
        # Clear and re-insert (consistent with previous Sheets logic)
        client.execute("DELETE FROM media_references")
        
        # Prepare batch insert
        columns = [
            "season", "episode_number", "episode_name", "episode_date", "guest",
            "media_type", "media_sub_category", "media_name", "url_to_media", 
            "mention_context", "image_url", "episode_url"
        ]
        
        placeholders = ", ".join(["?"] * len(columns))
        sql = f"INSERT INTO media_references ({', '.join(columns)}) VALUES ({placeholders})"
        
        # Convert df to list of tuples
        records = [tuple(x) for x in df[columns].values]
        
        # Batch execute using batch() for HTTP support
        batch_size = 50 # Slightly smaller batches for reliability over HTTP
        for i in range(0, len(records), batch_size):
            batch_records = records[i:i+batch_size]
            batch_statements = [(sql, record) for record in batch_records]
            try:
                client.batch(batch_statements)
            except Exception as e:
                print(f"      ERROR in batch {i//batch_size + 1}: {e}")
                # Fallback to individual inserts if batch fails
                for record in batch_records:
                    try:
                        client.execute(sql, record)
                    except Exception as inner_e:
                        print(f"      CRITICAL ERROR on record: {inner_e}")
                    
        print("Turso Database updated successfully.")
        client.close()
        return True
    except Exception as e:
        print(f"      ERROR syncing to Turso: {e}")
        return False

# --- MAIN ---

def main():
    summary = ExecutionSummary()
    parser = argparse.ArgumentParser(description="Gender Reveal Media Extraction Pipeline")
    parser.add_argument("--sync-only", action="store_true", help="Only run the Google Sheets synchronization step")
    parser.add_argument("--limit", type=int, help="Limit processing to N episodes")
    parser.add_argument("--skip-process", action="store_true", help="Skip scraping and AI processing, just sync if CSV exists")
    parser.add_argument("--backfill", action="store_true", help="Re-process episodes even if they are in the ledger (to fill in missing context)")
    parser.add_argument("--enrich", action="store_true", help="Fetch missing cover art for existing records in the CSV")
    args = parser.parse_args()

    if not GEMINI_API_KEY:
        print("Please set your GEMINI_API_KEY in the .env file.")
        return

    try:
        # 0. Optional Enrichment Mode
        if args.enrich:
            perf_log.info("Starting ENRICHMENT mode (Cover Art Lookup).")
            if os.path.exists(CSV_OUTPUT):
                enricher = MediaEnricher()
                # Load CSV and fill NaN with empty string to avoid issues
                df = pd.read_csv(CSV_OUTPUT).fillna("")
                
                # Find rows missing image_url
                mask = (df['image_url'] == "")
                missing_count = mask.sum()
                
                if missing_count > 0:
                    print(f"Found {missing_count} records missing cover art. Fetching...")
                    processed = 0
                    for idx, row in df[mask].iterrows():
                        if args.limit and processed >= args.limit:
                            break
                            
                        print(f"  [{processed+1}/{missing_count}] Fetching cover for: {row['media_name']} ({row['media_type']})")
                        img_url = enricher.fetch_image(row['media_name'], row['media_type'])
                        if img_url:
                            df.at[idx, 'image_url'] = img_url
                            print(f"    SUCCESS: {img_url}")
                        processed += 1
                        
                    df.to_csv(CSV_OUTPUT, index=False)
                    perf_log.info(f"Enrichment complete. Updated {processed} records.")
                else:
                    perf_log.info("No records found missing cover art.")
            else:
                perf_log.info("No CSV found to enrich.")
            
            # If ONLY doing enrichment, sync and exit
            if args.skip_process or args.sync_only:
                summary.sync_success = sync_to_turso(CSV_OUTPUT)
                summary.log_summary(perf_log)
                return

        # Handle sync-only early
        if args.sync_only:
            perf_log.info("Starting STANDALONE SYNC mode.")
            if os.path.exists(CSV_OUTPUT):
                try:
                    summary.sync_success = sync_to_turso(CSV_OUTPUT)
                except Exception as e:
                    error_log.error(f"Standalone Sync Failed: {e}\n{traceback.format_exc()}")
                    summary.errors_encountered += 1
            else:
                perf_log.info("No local CSV data found to sync.")
            summary.log_summary(perf_log)
            return

        perf_log.info(f"Starting PIPELINE run (Mode: {'BACKFILL' if args.backfill else 'STANDARD'}).")
        scraper = GenderRevealScraper(TRANSCRIPTS_DIR)
        extractor = MediaExtractor(GEMINI_API_KEY, TPM_LIMIT, RPM_LIMIT)
        enricher = MediaEnricher()
        state = PipelineState(PIPELINE_STATE_FILE, CSV_OUTPUT)
        data_fetcher = RSSDataFetcher()

        # 1. Scrape episode list
        perf_log.info("STEP 1: Scraping episode list...")
        episodes = scraper.scrape_episodes()
        summary.episodes_found = len(episodes)
        perf_log.info(f"Step 1 Complete: Found {summary.episodes_found} episodes.")

        # 2. Process episodes
        perf_log.info("STEP 2: Processing downloads and media extraction...")
        for i, ep in enumerate(episodes, 1):
            if args.limit and summary.episodes_processed >= args.limit:
                perf_log.info(f"Reached limit of {args.limit} episodes. Stopping processing.")
                break

            progress_prefix = f"[{i}/{summary.episodes_found}]"
            ep_display_name = f"Ep {ep['episode_number']}: {ep['episode_name']}"
            
            try:
                # Attach episode data from RSS
                rss_data = data_fetcher.get_data(ep['episode_number'], ep['episode_name'])
                ep['episode_date'] = rss_data['date']
                ep['episode_url'] = rss_data.get('link')
                show_notes = rss_data['show_notes']
                
                # Create a unique-ish filename
                safe_name = re.sub(r'[^\w\-_]', '_', ep['episode_name'])[:30]
                base_filename = f"ep_{ep['episode_number']}_{safe_name}"
                
                # Download
                full_filename = scraper.download_transcript(ep['transcript_url'], base_filename)
                if not full_filename:
                    print(f"{progress_prefix} SKIP: Failed to download transcript for {ep_display_name}")
                    continue
                    
                # Extract if not already processed OR if backfilling
                already_done = state.is_processed(full_filename)
                if not already_done or args.backfill:
                    if already_done:
                        print(f"\n{progress_prefix} BACKFILLING CONTEXT: {ep_display_name}")
                        state.remove_episode_from_csv(ep['episode_number'])
                    else:
                        print(f"\n{progress_prefix} PROCESSING: {ep_display_name}")
                    
                    text = scraper.extract_text(full_filename)
                    
                    if not text or len(text.strip()) < 100:
                        print(f"      WARNING: Transcript content too short. Skipping.")
                        state.mark_processed(full_filename)
                        continue

                    print(f"      AI ANALYSIS: Sending to Gemini...")
                    ep['guest'] = clean_guest_name(ep['episode_name']) 
                    media_refs = extractor.extract_from_text(text, ep, show_notes=show_notes)
                    
                    if media_refs:
                        # NEW: Automatically enrich new references with cover art
                        print(f"      ENRICHMENT: Fetching cover art for {len(media_refs)} items...")
                        for m in media_refs:
                            m['image_url'] = enricher.fetch_image(m['media_name'], m['media_type'])
                        
                        state.append_to_csv(media_refs)
                        summary.media_refs_extracted += len(media_refs)
                        print(f"      SUCCESS: Extracted and enriched {len(media_refs)} media references.")
                    
                    state.mark_processed(full_filename)
                    summary.episodes_processed += 1
                else:
                    summary.episodes_skipped += 1
                    if i % 20 == 0: # Periodic progress for skipped items
                        print(f"{progress_prefix} Skipping already processed episodes...")
            
            except Exception as e:
                error_msg = f"Error processing {ep_display_name}: {e}"
                print(f"      ERROR: {error_msg}")
                error_log.error(f"{error_msg}\n{traceback.format_exc()}")
                summary.errors_encountered += 1
                continue

        # 3. Final Sync to Turso Database
        perf_log.info("STEP 3: Synchronizing with Turso Database...")
        if os.path.exists(CSV_OUTPUT):
            try:
                summary.sync_success = sync_to_turso(CSV_OUTPUT)
                if summary.sync_success:
                    perf_log.info("Step 3 Complete: Turso Database updated.")
            except Exception as e:
                error_log.error(f"Sync Failed: {e}\n{traceback.format_exc()}")
                summary.errors_encountered += 1
        else:
            perf_log.info("Step 3 Skipped: No local CSV found.")

        summary.log_summary(perf_log)

    except KeyboardInterrupt:
        perf_log.info("Process interrupted by user.")
        print("\nProcess interrupted. Exiting gracefully...")
    except Exception as e:
        critical_error = f"CRITICAL PIPELINE FAILURE: {e}"
        print(f"\n{critical_error}")
        error_log.error(f"{critical_error}\n{traceback.format_exc()}")
        perf_log.error("Pipeline failed due to a critical error.")
        summary.log_summary(perf_log)
    finally:
        perf_log.info("Pipeline execution ended.")

if __name__ == "__main__":
    main()
