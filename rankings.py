"""National poll scraper (ncaa.com/rankings).

Finds UVM's current national ranking per sport: a number if Vermont is in the
poll, "RV" if it is listed under "Others receiving votes", otherwise nothing.

Opponents' ranks don't come from here: UVM's own schedule pages already show
them next to each opponent ("#7 Minnesota Duluth"), see uvm_dashboard.py.

NCAA.com has no women's ice hockey poll, so that sport has no UVM rank.

Usage on its own:
    python3 rankings.py
"""
from __future__ import annotations

import html
import re
from typing import Callable

BASE = "https://www.ncaa.com/rankings/"
TEAM = "Vermont"

# UVM sport slug -> NCAA.com rankings path (each redirects to that sport's main poll).
POLLS = {
    "mens-ice-hockey": "icehockey-men/d1",
    "mens-basketball": "basketball-men/d1/associated-press",
    "womens-basketball": "basketball-women/d1/associated-press",
    "mens-soccer": "soccer-men/d1",
    "womens-soccer": "soccer-women/d1",
    "mens-lacrosse": "lacrosse-men/d1",
    "womens-lacrosse": "lacrosse-women/d1",
}


def _text(fragment: str) -> str:
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', fragment))).strip()


def parse_poll(page: str) -> dict:
    """Return {poll, as_of, ranked: [{rank, team, record}], others: [team, ...]}."""
    # The poll name is the selected entry in the page's poll menu, e.g. "USCHO.com".
    title = re.search(r'<option[^>]*selected[^>]*>(.*?)</option>', page, re.S)
    as_of = re.search(r'class="rankings-last-updated"[^>]*>(.*?)</', page, re.S)
    ranked = []
    table = re.search(r'<table.*?</table>', page, re.S)
    if table:
        for row in re.findall(r'<tr.*?</tr>', table.group(0), re.S):
            cells = [_text(c) for c in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)]
            if len(cells) >= 2 and cells[0].isdigit():
                ranked.append({
                    "rank": cells[0],
                    "team": re.sub(r'\s*\(\d+\)$', '', cells[1]),  # drop first-place votes
                    "record": cells[2] if len(cells) > 2 else "",
                })
    others = []
    m = re.search(r'Others receiving votes:\s*(.*?)(?:</p>|<div|$)', page, re.S | re.I)
    if m:
        others = [re.sub(r'\s*\(\d+\)$', '', t).strip() for t in _text(m.group(1)).split(",")]
        others = [t for t in others if t]
    return {
        # "DI Men's Basketball: Associated Press" -> "Associated Press"
        "poll": _text(title.group(1)).split(":")[-1].strip() if title else "",
        # "Through Games NOV. 15, 2026" -> "through games Nov. 15, 2026"
        "as_of": re.sub(r'\b([A-Z])([A-Z]+)\b', lambda m: m.group(1) + m.group(2).lower(),
                        _text(as_of.group(1))).replace("Through Games", "through games") if as_of else "",
        "ranked": ranked,
        "others": others,
    }


def team_rank(poll: dict, team: str = TEAM) -> str:
    """'7' if ranked, 'RV' if receiving votes, '' otherwise."""
    for row in poll["ranked"]:
        if row["team"].lower() == team.lower():
            return row["rank"]
    return "RV" if any(t.lower() == team.lower() for t in poll["others"]) else ""


def rank_for(slug: str, fetch: Callable[[str], str]) -> dict | None:
    """UVM's rank info for a sport slug, or None if no poll is tracked for it."""
    path = POLLS.get(slug)
    if not path:
        return None
    poll = parse_poll(fetch(BASE + path))
    if not poll["ranked"]:
        return None
    return {
        "rank": team_rank(poll),
        "poll": poll["poll"],
        "as_of": poll["as_of"],
        "url": BASE + path,
    }


if __name__ == "__main__":
    import urllib.request

    def _fetch(url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (personal dashboard)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="replace")

    for slug in POLLS:
        info = rank_for(slug, _fetch)
        print(f"{slug:20} {(info or {}).get('rank') or '-':>3}  {(info or {}).get('poll', '')} · {(info or {}).get('as_of', '')}")
