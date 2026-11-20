#!/usr/bin/env python3
"""UVM Athletics dashboard.

Scrapes public data from uvmathletics.com (schedules/results, meet placements,
news RSS), americaeast.com (conference standings) and hockeyeastonline.com
(hockey standings, see hockey_east.py), then writes a self-contained
dashboard.html. Standard library only — no installs needed.

Usage:
    python3 uvm_dashboard.py            # fetch (using cache when fresh) and build
    python3 uvm_dashboard.py --refresh  # ignore the cache and refetch everything
    python3 uvm_dashboard.py --open     # build, then open in your browser
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import hockey_east

BASE = "https://uvmathletics.com"
CONF_BASE = "https://americaeast.com"
HERE = Path(__file__).resolve().parent
CACHE_DIR = HERE / ".cache"
OUT_FILE = HERE / "dashboard.html"
USER_AGENT = "Mozilla/5.0 (personal UVM scores dashboard; low-volume)"
CACHE_TTL = 30 * 60          # schedules, news, standings: 30 minutes
ID_CACHE_TTL = 24 * 60 * 60  # sport list and schedule ids: 1 day
REQUEST_DELAY = 0.4          # seconds between live requests, to be polite

# UVM sport slug -> America East standings path. Hockey standings come from
# hockey_east.py; XC/track/skiing/swim are meets with placements instead.
CONF_STANDINGS = {
    "mens-soccer": "msoc",
    "womens-soccer": "wsoc",
    "field-hockey": "fhockey",
    "mens-basketball": "mbball",
    "womens-basketball": "wbball",
    "mens-lacrosse": "mlax",
    "womens-lacrosse": "wlax",
}

FALLBACK_SPORTS = [
    "field-hockey", "mens-basketball", "mens-cross-country", "mens-ice-hockey",
    "mens-lacrosse", "mens-soccer", "mtrack", "skiing", "womens-basketball",
    "womens-cross-country", "womens-ice-hockey", "womens-lacrosse",
    "womens-soccer", "womens-swimming-and-diving", "wtrack",
]

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


# --------------------------------------------------------------------------- #
# Fetching with a small on-disk cache
# --------------------------------------------------------------------------- #
_last_request = 0.0


def fetch(url: str, ttl: int = CACHE_TTL, refresh: bool = False) -> str:
    global _last_request
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / (hashlib.sha1(url.encode()).hexdigest() + ".txt")
    if not refresh and path.exists() and time.time() - path.stat().st_mtime < ttl:
        return path.read_text(encoding="utf-8")
    wait = REQUEST_DELAY - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # network trouble: fall back to stale cache
        _last_request = time.time()
        if path.exists():
            print(f"  ! {url}: {exc} (using stale cache)", file=sys.stderr)
            return path.read_text(encoding="utf-8")
        raise
    _last_request = time.time()
    path.write_text(text, encoding="utf-8")
    return text


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class Game:
    sport: str
    date: str | None          # ISO date or None if TBA
    date_label: str
    time: str
    home_away: str
    opponent: str
    location: str
    tournament: str
    result: str
    outcome: str              # "W", "L", "T" or ""
    place: str = ""           # team finish at a meet, e.g. "1st, 30 Pts"
    links: dict[str, str] = field(default_factory=dict)  # "Recap"/"Results"/"Box Score" -> URL


@dataclass
class Sport:
    slug: str
    name: str
    season: str = ""
    records: dict[str, str] = field(default_factory=dict)
    games: list[Game] = field(default_factory=list)
    standings: list[dict[str, str]] = field(default_factory=list)
    standings_source: str = ""
    standings_url: str = ""
    schedule_url: str = ""
    error: str = ""


@dataclass
class NewsItem:
    title: str
    link: str
    sport: str
    published: str
    summary: str
    image: str


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def discover_sports(refresh: bool) -> list[str]:
    try:
        page = fetch(f"{BASE}/sports/mens-soccer/schedule", ID_CACHE_TTL, refresh)
        slugs = sorted(set(re.findall(r'/sports/([a-z0-9-]+)/schedule', page)))
        return slugs or FALLBACK_SPORTS
    except Exception:
        return FALLBACK_SPORTS


def schedule_id(page: str) -> str | None:
    m = re.search(r'schedule_txt\.ashx\?schedule=(\d+)', page)
    return m.group(1) if m else None


def _text(fragment: str) -> str:
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', fragment))).strip()


LINK_LABELS = [  # (pattern on link text/url, label shown on the dashboard)
    (r'box ?score', "Box Score"),
    (r'result', "Results"),
    (r'recap', "Recap"),
    (r'stats', "Stats"),
]


def parse_schedule_html(page: str) -> list[dict]:
    """Per-game extras from the rendered schedule page.

    The text export has W/L scores but not meet placements ("1st, 30 Pts") or
    links to recaps and results PDFs, so pull those from the HTML blocks.
    """
    starts = [m.start() for m in re.finditer(r'<li[^>]*class="sidearm-schedule-game ', page)]
    games = []
    for a, b in zip(starts, starts[1:] + [len(page)]):
        block = page[a:b]
        name = re.search(r'sidearm-schedule-game-opponent-name[^>]*>(.*?)</div>', block, re.S)
        date_m = re.search(r'sidearm-schedule-game-opponent-date[^>]*>\s*<span[^>]*>(.*?)</span>', block, re.S)
        res = re.search(r'sidearm-schedule-game-result[^>]*>(.*?)</div>', block, re.S)
        spans = [_text(s) for s in re.findall(r'<span[^>]*>(.*?)</span>', res.group(1), re.S)] if res else []
        place = next((s for s in spans if re.match(r'\d+(st|nd|rd|th)\b', s)), "")
        links: dict[str, str] = {}
        for href, label in re.findall(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S):
            label_text = _text(label)
            for pat, nice in LINK_LABELS:
                if nice not in links and re.search(pat, label_text, re.I):
                    links[nice] = href if href.startswith("http") else BASE + href
                    break
        games.append({
            "opponent": _text(name.group(1)) if name else "",
            "date_label": _text(date_m.group(1)) if date_m else "",
            "place": place,
            "links": links,
        })
    return games


def merge_html_extras(sport: Sport, extras: list[dict]) -> None:
    """Attach placements and links to games parsed from the text export."""
    if len(extras) == len(sport.games):
        pairs = zip(sport.games, extras)  # same order on both pages
    else:  # fall back to matching on date + opponent
        index = {(e["date_label"][:6], e["opponent"].lower()): e for e in extras}
        pairs = ((g, index.get((g.date_label[:6], g.opponent.lower()))) for g in sport.games)
    for game, extra in pairs:
        if not extra:
            continue
        game.place = extra["place"]
        game.links = extra["links"]
        # Meets list a placeholder "W 0-0" score; replace it with the placement.
        if game.place and (not game.result or re.fullmatch(r'[WLT] 0-0', game.result)):
            game.result = game.place
            game.outcome = ""


def season_years(season: str) -> tuple[int, int]:
    """'2026-27' -> (2026, 2027); '2026' -> (2026, 2026)."""
    m = re.search(r'(\d{4})(?:-(\d{2,4}))?', season)
    if not m:
        y = date.today().year
        return y, y
    start = int(m.group(1))
    if m.group(2):
        end = int(m.group(2))
        end = end + 2000 if end < 100 else end
        return start, end
    return start, start


def parse_date(label: str, years: tuple[int, int]) -> str | None:
    m = re.match(r'([A-Z][a-z]{2})\w*\.?\s+(\d{1,2})', label)
    if not m or m.group(1) not in MONTHS:
        return None
    month, day = MONTHS[m.group(1)], int(m.group(2))
    start, end = years
    # Split seasons: fall months belong to the first year, spring to the second.
    year = start if (start == end or month >= 7) else end
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def normalize_time(raw: str) -> str:
    """'6:00 PM', '1 P.M.', '7 p.m,' -> '6 p.m.', '1 p.m.', '7 p.m.'; 'TBA' etc. unchanged."""
    s = raw.strip()
    m = re.fullmatch(r'(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?[,.]?', s, re.I)
    if not m:
        return s.rstrip(",")
    hour, minute, ampm = m.groups()
    minutes = f":{minute}" if minute and minute != "00" else ""
    return f"{int(hour)}{minutes} {ampm.lower()}.m."


def parse_schedule_txt(slug: str, text: str) -> Sport:
    lines = text.splitlines()
    name, season = slug, ""
    title_line = next((l for l in lines[1:4] if "Schedule" in l), "")
    m = re.match(r'\s*(\S+)\s+(.*?)\s+Schedule', title_line)
    if m:
        season, name = m.group(1), m.group(2)
    sport = Sport(slug=slug, name=name, season=season,
                  schedule_url=f"{BASE}/sports/{slug}/schedule")

    header_idx = None
    for i, line in enumerate(lines):
        rec = re.match(r'(Overall|Conference|Streak|Home|Away|Neutral)\s+(\S+)', line)
        if rec and header_idx is None:
            sport.records[rec.group(1)] = rec.group(2)
        if line.startswith("Date") and "Opponent" in line:
            header_idx = i
            break
    if header_idx is None:
        return sport

    header = lines[header_idx]
    cols = [(m.group(0), m.start()) for m in re.finditer(r'\S+(?: \S+)*', header)]
    years = season_years(season)
    for line in lines[header_idx + 1:]:
        if not line.strip():
            continue
        row = {}
        for j, (col, start) in enumerate(cols):
            end = cols[j + 1][1] if j + 1 < len(cols) else None
            row[col] = line[start:end].strip() if start < len(line) else ""
        result = row.get("Result", "")
        outcome = result[0] if re.match(r'[WLT]\b', result) else ""
        label = row.get("Date", "")
        sport.games.append(Game(
            sport=slug,
            date=parse_date(label, years),
            date_label=label,
            time=normalize_time(row.get("Time", "")),
            home_away=row.get("At", ""),
            opponent=row.get("Opponent", ""),
            location=row.get("Location", ""),
            tournament=row.get("Tournament", ""),
            result=result,
            outcome=outcome,
        ))
    return sport


def parse_standings(page: str) -> list[dict[str, str]]:
    table = re.search(r'<table.*?</table>', page, re.S)
    if not table:
        return []

    def cells(row: str) -> list[str]:
        raw = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.S)
        return [re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', c))).strip()
                for c in raw]

    rows = re.findall(r'<tr.*?</tr>', table.group(0), re.S)
    if not rows:
        return []
    header = cells(rows[0])
    # Sidearm repeats each column for mobile/desktop; drop the duplicate twin.
    norm = [h.lower().replace(".", "").strip() for h in header]
    keep = [i for i in range(len(header)) if i == 0 or norm[i] != norm[i - 1]]
    names = [header[i].title() for i in keep]
    out = []
    for row in rows[1:]:
        c = cells(row)
        if len(c) != len(header):
            continue
        entry = {names[k]: c[i] for k, i in enumerate(keep)}
        first = names[0]
        entry[first] = re.sub(r'\s+-\w+$', '', entry[first])  # strip "-x" clinch tags
        out.append(entry)
    return out


def parse_news(xml_text: str, limit: int = 20) -> list[NewsItem]:
    ns = {"media": "http://search.yahoo.com/mrss/"}
    items = []
    root = ET.fromstring(xml_text)
    for it in root.iter("item"):
        desc_html = it.findtext("description") or ""
        text = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', desc_html))).strip()
        thumb = it.find("media:thumbnail", ns)
        pub = it.findtext("pubDate") or ""
        try:
            published = parsedate_to_datetime(pub).isoformat()
        except Exception:
            published = pub
        items.append(NewsItem(
            title=html.unescape(it.findtext("title") or "").strip(),
            link=it.findtext("link") or "",
            sport=it.findtext("category") or "",
            published=published,
            summary=text[:240] + ("…" if len(text) > 240 else ""),
            image=thumb.get("url") if thumb is not None else "",
        ))
        if len(items) >= limit:
            break
    return items


# --------------------------------------------------------------------------- #
# Collect everything
# --------------------------------------------------------------------------- #
def collect(refresh: bool) -> dict:
    sports: list[Sport] = []
    seen_ids: set[str] = set()
    # The site sometimes links one team under two slugs (e.g. "mens-soccer" and
    # "msoc"). Try the known full slugs first, then skip any schedule already seen.
    slugs = sorted(discover_sports(refresh), key=lambda s: (s not in FALLBACK_SPORTS, s))
    for slug in slugs:
        print(f"  {slug}")
        try:
            sched_page = fetch(f"{BASE}/sports/{slug}/schedule", refresh=refresh)
            sid = schedule_id(sched_page)
            if not sid:
                sports.append(Sport(slug=slug, name=slug, error="No schedule found"))
                continue
            if sid in seen_ids:
                print(f"    duplicate of an earlier sport (schedule {sid}), skipping")
                continue
            seen_ids.add(sid)
            txt = fetch(f"{BASE}/services/schedule_txt.ashx?schedule={sid}", refresh=refresh)
            sport = parse_schedule_txt(slug, txt)
            merge_html_extras(sport, parse_schedule_html(sched_page))
            try:
                if slug in CONF_STANDINGS:
                    url = f"{CONF_BASE}/standings.aspx?path={CONF_STANDINGS[slug]}"
                    sport.standings = parse_standings(fetch(url, refresh=refresh))
                    sport.standings_source, sport.standings_url = "America East", url
                elif slug in hockey_east.PATHS:
                    sport.standings = hockey_east.standings_for(
                        slug, lambda u: fetch(u, refresh=refresh))
                    sport.standings_source = "Hockey East"
                    sport.standings_url = hockey_east.source_url(slug)
            except Exception as exc:
                print(f"    standings failed: {exc}", file=sys.stderr)
            sports.append(sport)
        except Exception as exc:
            print(f"    failed: {exc}", file=sys.stderr)
            sports.append(Sport(slug=slug, name=slug, error=str(exc)))

    try:
        news = parse_news(fetch(f"{BASE}/rss.aspx", refresh=refresh))
    except Exception as exc:
        print(f"  news failed: {exc}", file=sys.stderr)
        news = []

    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "today": date.today().isoformat(),
        "sports": [asdict(s) for s in sports],
        "news": [asdict(n) for n in news],
    }


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #
def render(data: dict) -> str:
    template = (HERE / "dashboard_template.html").read_text(encoding="utf-8")
    payload = json.dumps(data).replace("</", "<\\/")
    return template.replace("/*__DATA__*/null", payload)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--refresh", action="store_true", help="ignore cache")
    ap.add_argument("--open", action="store_true", help="open dashboard when done")
    args = ap.parse_args()

    print("Fetching UVM athletics data…")
    data = collect(args.refresh)
    (HERE / "data.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    OUT_FILE.write_text(render(data), encoding="utf-8")
    games = sum(len(s["games"]) for s in data["sports"])
    print(f"Wrote {OUT_FILE.name}: {len(data['sports'])} sports, {games} games, "
          f"{len(data['news'])} news items")
    if args.open:
        webbrowser.open(OUT_FILE.as_uri())


if __name__ == "__main__":
    main()
