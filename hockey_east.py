"""Hockey East standings scraper (hockeyeastonline.com).

UVM's men's and women's ice hockey teams play in Hockey East, which is not on
the Sidearm platform the America East site uses. Its standings pages are plain
server-rendered HTML with a single ``<table class="data">``.

Usage on its own:
    python3 hockey_east.py           # prints men's and women's standings
"""
from __future__ import annotations

import html
import re
from typing import Callable

BASE = "https://hockeyeastonline.com"
PATHS = {
    "mens-ice-hockey": "/men/standings/index.php",
    "womens-ice-hockey": "/women/standings/index.php",
}

# Raw column order in the table:
#   rank, team, GP, PTS, W, L, T, OW, OL, SW, GF, GA, (spacer), GP, W, L, T, GF, GA
#   |------------------ conference -------------------|        |----- overall -----|


def _cells(row: str) -> list[str]:
    raw = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.S)
    return [re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', c))).strip()
            for c in raw]


def parse_standings(page: str) -> list[dict[str, str]]:
    table = re.search(r'<table class="data".*?</table>', page, re.S)
    if not table:
        return []
    out = []
    for row in re.findall(r'<tr.*?</tr>', table.group(0), re.S):
        c = _cells(row)
        # Data rows have the full 19 columns and a numeric GP. The rank cell is
        # sometimes blank on the site, so number rows by position instead.
        if len(c) < 19 or not c[1] or not c[2].isdigit():
            continue
        out.append({
            "#": str(len(out) + 1),
            "School": c[1],
            "GP": c[2],
            "Pts": c[3],
            "Conf": f"{c[4]}-{c[5]}-{c[6]}",
            "OW-OL-SW": f"{c[7]}-{c[8]}-{c[9]}",
            "GF": c[10],
            "GA": c[11],
            "Overall": f"{c[14]}-{c[15]}-{c[16]}",
            "Ovr GF": c[17],
            "Ovr GA": c[18],
        })
    return out


def standings_for(slug: str, fetch: Callable[[str], str]) -> list[dict[str, str]]:
    """Return Hockey East standings for a UVM sport slug, or [] if not hockey."""
    path = PATHS.get(slug)
    return parse_standings(fetch(BASE + path)) if path else []


def source_url(slug: str) -> str:
    return BASE + PATHS[slug] if slug in PATHS else ""


if __name__ == "__main__":
    import urllib.request

    def _fetch(url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (personal dashboard)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="replace")

    for slug in PATHS:
        print(f"\n{slug}")
        for row in standings_for(slug, _fetch):
            print("  " + "  ".join(f"{v:>14}" if k == "School" else f"{v:>6}" for k, v in row.items()))
