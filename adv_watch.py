import json
from pathlib import Path
from datetime import datetime, timezone
import requests

STATE_FILE = Path("adv_watch_state.json")

CRD = 307151
PDF_URL = f"https://reports.adviserinfo.sec.gov/reports/ADV/{CRD}/PDF/{CRD}.pdf"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))

def head_pdf(url: str) -> dict:
    r = requests.head(url, headers=HEADERS, timeout=30, allow_redirects=True)
    r.raise_for_status()
    h = r.headers
    return {
        "etag": h.get("ETag"),
        "last_modified": h.get("Last-Modified"),
        "content_length": h.get("Content-Length"),
        "content_type": h.get("Content-Type"),
        "final_url": str(r.url),
        "status_code": r.status_code,
    }

def main():
    state = load_state()
    prev = state.get("elliott", {})

    cur = head_pdf(PDF_URL)

    # Prefer ETag; fallback to Last-Modified; fallback to Content-Length
    cur_sig = cur.get("etag") or cur.get("last_modified") or cur.get("content_length")
    prev_sig = prev.get("sig")

    state["elliott"] = {
        "last_checked_utc": utc_now(),
        "pdf_url": PDF_URL,
        "sig": cur_sig,
        "headers": cur,
    }
    save_state(state)

    if prev_sig is None:
        print(f"First run baseline stored: {cur_sig}")
        return

    if cur_sig != prev_sig:
        Path("CHANGED.txt").write_text(
            "Elliott ADV PDF changed\n"
            f"Previous signature: {prev_sig}\n"
            f"Current signature : {cur_sig}\n"
            f"PDF URL: {PDF_URL}\n"
        )
        print("CHANGED")
    else:
        print("NO CHANGE")

if __name__ == "__main__":
    main()
