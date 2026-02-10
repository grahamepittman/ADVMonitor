import json
import re
from pathlib import Path
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

STATE_FILE = Path("adv_watch_state.json")

ANCHOR_URL = (
    "https://files.adviserinfo.sec.gov/IAPD/content/viewform/adv/Sections/"
    "iapd_AdvSignatureSection.aspx?ORG_PK=307151&FLNG_PK=041FF834000801ED05AF6222003D7CD9056C8CC0"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}

def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))

def fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def extract_filing_date(html: str) -> str:
    """
    Extract a MM/DD/YYYY date from the signature page.

    We intentionally do this in a robust way:
    - Convert the page to plain text
    - Look for the first MM/DD/YYYY
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # Match MM/DD/YYYY
    m = re.search(r"\b(0[1-9]|1[0-2])/(0[1-9]|[12][0-9]|3[01])/\d{4}\b", text)
    if not m:
        raise RuntimeError("Could not locate a filing date in signature page HTML.")

    return m.group(0)

def main():
    state = load_state()
    prev = state.get("elliott", {})

    html = fetch_html(ANCHOR_URL)
    filing_date = extract_filing_date(html)

    prev_date = prev.get("filing_date")

    # Store state every run
    state["elliott"] = {
        "last_checked_utc": utc_now(),
        "filing_date": filing_date,
        "anchor_url": ANCHOR_URL,
    }
    save_state(state)

    # First run = establish baseline, no alert
    if prev_date is None:
        print(f"First run baseline stored: {filing_date}")
        return

    if filing_date != prev_date:
        Path("CHANGED.txt").write_text(
            f"Elliott ADV signature date changed: {prev_date} -> {filing_date}\n"
            f"{ANCHOR_URL}\n"
        )
        print("CHANGED")
    else:
        print("NO CHANGE")

if __name__ == "__main__":
    main()
