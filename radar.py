#!/usr/bin/env python3
"""
Opportunity Radar - lightweight funding/procurement intelligence tracker.

Fetches configured sources (AusTender, GrantConnect, DFAT pages, DAP pages,
ACIAR, managing-contractor news), extracts link items, scores them against
geography/theme keywords, diffs against previously-seen items, and writes a
markdown digest with pre-positioning suggestions from the playbook.

Usage:
    python radar.py                 # normal run
    python radar.py --dry-run       # don't update the seen store
    python radar.py --rescan        # ignore seen store (show everything)

State:   data/seen.json
Output:  digests/YYYY-MM-DD.md  and  digests/latest.md
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
import yaml
from bs4 import BeautifulSoup

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

ROOT = Path(__file__).parent
SEEN_PATH = ROOT / "data" / "seen.json"
DIGEST_DIR = ROOT / "digests"

# Link text shorter than this is treated as navigation chrome, not content
MIN_TITLE_LEN = 18
# Common nav noise to skip even if long enough
NAV_NOISE = re.compile(
    r"^(home|about|contact|login|register|privacy|terms|sitemap|skip to|"
    r"accessibility|copyright|feedback|search|menu|back to top)",
    re.IGNORECASE,
)


# ----------------------------------------------------------------------
# Loading and state
# ----------------------------------------------------------------------

def load_config():
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_seen():
    if SEEN_PATH.exists():
        with open(SEEN_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_seen(seen):
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=1, ensure_ascii=False)


def item_key(title, url):
    return hashlib.sha1(f"{title.strip().lower()}|{url}".encode()).hexdigest()[:16]


# ----------------------------------------------------------------------
# Fetching and extraction
# ----------------------------------------------------------------------

def fetch(url, cfg):
    headers = {"User-Agent": cfg["settings"]["user_agent"]}
    resp = requests.get(url, headers=headers,
                        timeout=cfg["settings"]["request_timeout"])
    resp.raise_for_status()
    return resp


def extract_html_items(html, base_url):
    """Extract (title, url) candidates from a page: links with real text."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    items, seen_local = [], set()
    for a in soup.find_all("a", href=True):
        title = " ".join(a.get_text(" ", strip=True).split())
        href = a["href"].strip()
        if len(title) < MIN_TITLE_LEN or NAV_NOISE.match(title):
            continue
        if href.startswith(("javascript:", "mailto:", "#")):
            continue
        full = urljoin(base_url, href)
        k = (title.lower(), full)
        if k in seen_local:
            continue
        seen_local.add(k)
        items.append({"title": title, "url": full})
    return items


def extract_rss_items(content):
    if not HAS_FEEDPARSER:
        return []
    feed = feedparser.parse(content)
    return [{"title": e.get("title", "").strip(),
             "url": e.get("link", "")} for e in feed.entries
            if e.get("title")]


# ----------------------------------------------------------------------
# Scoring and playbook
# ----------------------------------------------------------------------

def score_item(title, kw, geo_optional):
    """Return (score, matched_terms) or (0, []) if excluded/unqualified."""
    text = " " + title.lower() + " "
    for bad in kw.get("exclude", []):
        if bad in text:
            return 0, []

    matched, score = [], 0
    geo_hits = [t for t in kw["geography"]["terms"] if t in text]
    theme_hits = [t for t in kw["themes"]["terms"] if t in text]
    boost_hits = [t for t in kw.get("boosters", {}).get("terms", []) if t in text]

    score += len(geo_hits) * kw["geography"]["weight"]
    score += len(theme_hits) * kw["themes"]["weight"]
    score += len(boost_hits) * kw.get("boosters", {}).get("weight", 0)
    matched = geo_hits + theme_hits + boost_hits

    # Require a geography hit unless the source already implies our region
    if not geo_hits and not geo_optional:
        return 0, []
    # Require at least some substantive signal
    if not theme_hits and not boost_hits and not geo_hits:
        return 0, []
    return score, matched


def playbook_lookup(title, playbook):
    """Return list of (likely_actors, actions) entries whose triggers match."""
    text = title.lower()
    hits = []
    for entry in playbook:
        if any(t in text for t in entry["trigger"]):
            hits.append(entry)
    return hits


def band(score, cfg):
    s = cfg["settings"]
    if score >= s["high_threshold"]:
        return "HIGH"
    if score >= s["medium_threshold"]:
        return "MEDIUM"
    return "LOW"


# ----------------------------------------------------------------------
# Digest
# ----------------------------------------------------------------------

def write_digest(new_items, errors, manual_sources, cfg, run_date):
    lines = [
        f"# Opportunity Radar - {run_date.isoformat()}",
        "",
        f"New items this run: **{len(new_items)}**  |  "
        f"Sources with errors: {len(errors)}",
        "",
    ]

    if new_items:
        new_items.sort(key=lambda x: -x["score"])
        lines += [
            "| Relevance | Opportunity / signal | Source | Matched terms | Link |",
            "|---|---|---|---|---|",
        ]
        for it in new_items:
            terms = ", ".join(it["matched"][:6])
            lines.append(
                f"| {band(it['score'], cfg)} ({it['score']}) "
                f"| {it['title'][:120]} "
                f"| {it['source']} "
                f"| {terms} "
                f"| [open]({it['url']}) |"
            )
        lines.append("")

        # Pre-positioning section for HIGH and MEDIUM items
        actionable = [i for i in new_items
                      if band(i["score"], cfg) in ("HIGH", "MEDIUM")
                      and i["playbook"]]
        if actionable:
            lines.append("## Pre-positioning actions")
            lines.append("")
            for it in actionable:
                lines.append(f"### {it['title'][:120]}")
                for pb in it["playbook"]:
                    lines.append(f"- **Likely actors:** {pb['likely_actors']}")
                    lines.append(f"- **Do now:** {pb['actions'].strip()}")
                lines.append("")
    else:
        lines.append("_No new scored items this run. "
                     "Quiet weeks are normal; the manual checklist below still applies._")
        lines.append("")

    if manual_sources:
        lines.append("## Manual checklist (login-walled or bot-blocked)")
        lines.append("")
        for m in manual_sources:
            note = f" - {m.get('notes', '')}" if m.get("notes") else ""
            lines.append(f"- [ ] [{m['name']}]({m['url']}){note}")
        lines.append("")

    if errors:
        lines.append("## Source errors (check manually this week)")
        lines.append("")
        for name, err in errors:
            lines.append(f"- **{name}**: {err}")
        lines.append("")

    lines.append("---")
    lines.append("_Generated by Opportunity Radar. Tune keywords, sources and the "
                 "playbook in `config.yaml`._")

    DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    body = "\n".join(lines)
    (DIGEST_DIR / f"{run_date.isoformat()}.md").write_text(body, encoding="utf-8")
    (DIGEST_DIR / "latest.md").write_text(body, encoding="utf-8")
    return body


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="don't update the seen store")
    ap.add_argument("--rescan", action="store_true",
                    help="ignore the seen store and score everything")
    args = ap.parse_args()

    cfg = load_config()
    kw = cfg["keywords"]
    playbook = cfg.get("playbook", [])
    seen = {} if args.rescan else load_seen()
    run_date = date.today()

    new_items, errors, manual_sources = [], [], []
    first_run_sources = set()

    for src in cfg["sources"]:
        if src["type"] == "manual":
            manual_sources.append(src)
            continue
        try:
            resp = fetch(src["url"], cfg)
            if src["type"] == "rss":
                items = extract_rss_items(resp.content)
            else:
                items = extract_html_items(resp.text, src["url"])
        except Exception as e:  # noqa: BLE001 - report any fetch failure
            errors.append((src["name"], f"{type(e).__name__}: {e}"))
            # Fall back: surface it as a manual item so it isn't silently lost
            manual_sources.append(src)
            continue

        src_seen_before = any(v.get("source") == src["name"] for v in seen.values())
        if not src_seen_before and not args.rescan:
            first_run_sources.add(src["name"])

        for it in items:
            key = item_key(it["title"], it["url"])
            if key in seen:
                continue
            score, matched = score_item(it["title"], kw,
                                        src.get("geo_optional", False))
            seen[key] = {"title": it["title"], "url": it["url"],
                         "source": src["name"],
                         "first_seen": run_date.isoformat(),
                         "score": score}
            # On a source's first-ever run, baseline silently (everything is
            # "new"); from the second run onward, genuinely new items surface.
            if src["name"] in first_run_sources:
                continue
            if score >= cfg["settings"]["min_score"]:
                new_items.append({**it, "source": src["name"], "score": score,
                                  "matched": matched,
                                  "playbook": playbook_lookup(it["title"],
                                                              playbook)})

    body = write_digest(new_items, errors, manual_sources, cfg, run_date)

    if not args.dry_run:
        save_seen(seen)

    if first_run_sources:
        print(f"Baselined {len(first_run_sources)} source(s) on first run "
              f"(items recorded, digest starts next run): "
              f"{', '.join(sorted(first_run_sources))}", file=sys.stderr)
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
