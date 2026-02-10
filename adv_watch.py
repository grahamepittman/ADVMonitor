import json
import re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

STATE_FILE = Path("adv_watch_state.json")

CRD = 307151
FIRM_SUMMARY_URL = f"https://adviserinfo.sec.gov/firm/summary/{CRD}"

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

def extract_latest_viewform_link(summary_html: str) -> str:
    """
    From the firm summary page, extract a link containing ORG_PK and FLNG_PK.
    This is the "View Latest Form ADV Filed" style link.
    """
    soup = BeautifulSoup(summary_html, "html.parser")

    # Look for any link containing FLNG_PK
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "FLNG_PK=" in href and "ORG_PK=" in href:
            # normalize relative URLs
            if href.startswith("/"):
                return "https://adviserinfo.sec.gov" + href
            if href.startswith("http"):
                return href

    # Fallback: regex
    m = re.search(r'(https?://[^"\']+ORG_PK=\d+[^"\']*FLNG_PK=[A-Za-z0-9]+[^"\']*)', summary_html)
    if m:
        return m.group(1).replace("&amp;", "&")

    raise RuntimeError("Could not find latest ADV viewform link on firm summary page.")

def extract_org_and_flng(url: str) -> tuple[str, str]:
    """
    Parse ORG_PK and FLNG_PK from a URL query string.
    """
    q = parse_qs(urlparse(url).query)
    org = q.get("ORG_PK", [None])[0]
    flng = q.get("FLNG_PK", [None])[0]
    if not org or not flng:
        raise RuntimeError(f"Could not parse ORG_PK/FLNG_PK from URL: {url}")
    return org, flng

def build_signature_url(org_pk: str, flng_pk: str) -> str:
    """
    Build the signature section URL for the current filing.
    """
    return (
        "https://files.adviserinfo.sec.gov/IAPD/content/viewform/adv/Sections/"
        f"iapd_AdvSignatureSection.aspx?ORG_PK={org_pk}&FLNG_PK={flng_pk}"
    )

def extract_filing_date(signature_html: str) -> str:
    """
    Extract MM/DD/YYYY from the signature page text.
    """
    soup = BeautifulSoup(signature_html, "html.parser")
    text = soup.get_text(" ", strip=True)

    m = re.search(r"\b(0[1-9]|1[0-2])/(0[1-9]|[12][0-9]|3[01])/\d{4}\b", text)
    if not m:
        raise RuntimeError("Could not locate a MM/DD/YYYY date in signature page HTML.")
    return m.group(0)

def main():
    state = load_state()
    prev = state.get("elliott", {})

    # 1) Discover current filing (ORG_PK + FLNG_PK)
    summary_html = fetch_html(FIRM_SUMMARY_URL)
    viewform_url = extract_latest_viewform_link(summary_html)
    org_pk, flng_pk = extract_org_and_flng(viewform_url)

    # 2) Scrape signature page for filing date
    signature_url = build_signature_url(org_pk, flng_pk)
    sig_html = fetch_html(signature_url)
    filing_date = extract_filing_date(sig_html)

    prev_date = prev.get("filing_date")
    prev_flng = prev.get("flng_pk")

    # Always update state
    state["elliott"] = {
        "last_checked_utc": utc_now(),
        "crd": CRD,
        "org_pk": org_pk,
        "flng_pk": flng_pk,
        "filing_date": filing_date,
        "firm_summary_url": FIRM_SUMMARY_URL,
        "viewform_url_found": viewform_url,
        "signature_url_used": signature_url,
    }
    save_state(state)

    # First run: baseline
    if prev_date is None:
        print(f"First run baseline stored: {filing_date} ({flng_pk})")
        return

    # Change detection
    changed = (filing_date != prev_date) or (flng_pk != prev_flng)

    if changed:
        Path("CHANGED.txt").write_text(
            f"Elliott ADV changed\n"
            f"Previous date: {prev_date}\n"
            f"Current date : {filing_date}\n"
            f"Previous FLNG_PK: {prev_flng}\n"
            f"Current FLNG_PK : {flng_pk}\n\n"
            f"Signature URL:\n{signature_url}\n"
        )
        print("CHANGED")
    else:
        print("NO CHANGE")

if __name__ == "__main__":
    main()
