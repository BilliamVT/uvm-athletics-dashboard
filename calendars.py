"""Subscribable calendars (.ics) for each UVM team, plus one for all teams.

Written to calendars/<slug>.ics and calendars/all.ics on every build and
published with the site. Subscribing (rather than importing) means your
calendar app re-checks the file every few hours, so new games, time changes
and final scores show up on their own.

Times on UVM's site are Eastern; games with "TBA"/"TBD" times become all-day
events. Past games get the result in the title ("W 4-2 vs Brock").
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    EASTERN = ZoneInfo("America/New_York")
except Exception:  # no tz database: fall back to "floating" local times
    EASTERN = None

# Rough event lengths, so games block out sensible time in the calendar.
DURATIONS = {"ice-hockey": 2.5, "basketball": 2.0, "lacrosse": 2.0, "soccer": 2.0, "field-hockey": 1.75}
MEET_HOURS = 3.0
DEFAULT_HOURS = 2.0


def _short(name: str) -> str:
    return name.replace("Women's ", "W ").replace("Men's ", "M ").replace(" and Diving", "").replace("Track & Field", "Track")


def _escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> str:
    """Fold lines longer than 75 octets (RFC 5545), without splitting UTF-8 characters."""
    out, cur = [], ""
    for ch in line:
        limit = 75 if not out else 74  # continuation lines start with a space
        if len((cur + ch).encode("utf-8")) > limit:
            out.append(cur)
            cur = ch
        else:
            cur += ch
    out.append(cur)
    return "\r\n ".join(out)


def _parse_time(label: str) -> tuple[int, int] | None:
    m = re.fullmatch(r'(\d{1,2})(?::(\d{2}))?\s*([AP])M', label.strip(), re.I)
    if not m:
        return None
    hour, minute = int(m.group(1)) % 12, int(m.group(2) or 0)
    if m.group(3).upper() == "P":
        hour += 12
    return hour, minute


def _hours_for(slug: str, is_meet: bool) -> float:
    if is_meet:
        return MEET_HOURS
    return next((h for key, h in DURATIONS.items() if key in slug), DEFAULT_HOURS)


def _fmt_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _event_lines(sport: dict, game: dict, stamp: str) -> list[str]:
    slug = sport["slug"]
    day = date.fromisoformat(game["date"])
    is_meet = not sport["records"].get("Overall")
    where = "" if is_meet else ("at " if game["home_away"] == "Away" else "vs ")
    opp = ("#" + game["opp_rank"] + " " if game.get("opp_rank") else
           "(" + game["opp_seed"] + ") " if game.get("opp_seed") else "") + game["opponent"]
    # Finished games lead with the outcome so it's visible even in a cut-off title,
    # like the official UVM calendars: "[W] UVM M Ice Hockey vs Brock (4-2)".
    # Meets lead with the team finish: "[1st] UVM W Cross Country: Fall Foliage Invite (30 Pts)".
    result, outcome = game.get("result", ""), game.get("outcome", "")
    team = f"UVM {_short(sport['name'])}"
    if outcome and result.startswith(outcome):
        score = result[len(outcome):].strip()
        detail = ", ".join(x for x in (score, game.get("result_note", "")) if x)
        summary = f"[{outcome}] {team} {where}{opp}" + (f" ({detail})" if detail else "")
    elif game.get("place"):
        rank, _, pts = game["place"].partition(",")
        summary = f"[{rank.strip()}] {team}: {opp}" + (f" ({pts.strip()})" if pts.strip() else "")
    else:
        summary = f"{team}: {where}{opp}" if is_meet else f"{team} {where}{opp}"

    details = []
    if game.get("tv"):
        details.append(f"Watch: {game['tv']}")
    if game.get("radio"):
        details.append(f"Radio: {game['radio']}")
    if game.get("tournament"):
        details.append(f"Tournament: {game['tournament']}")
    for label, url in game.get("links", {}).items():
        details.append(f"{label}: {url}")
    details.append(f"Schedule: {sport['schedule_url']}")

    uid_opp = re.sub(r'[^a-z0-9]+', '-', game["opponent"].lower()).strip("-")
    lines = [
        "BEGIN:VEVENT",
        f"UID:{slug}-{game['date']}-{uid_opp}@uvm-athletics-dashboard",
        f"DTSTAMP:{stamp}",
    ]
    hm = _parse_time(game.get("time", ""))
    if hm:
        start = datetime(day.year, day.month, day.day, hm[0], hm[1], tzinfo=EASTERN)
        end = start + timedelta(hours=_hours_for(slug, is_meet))
        if EASTERN:
            lines += [f"DTSTART:{_fmt_utc(start)}", f"DTEND:{_fmt_utc(end)}"]
        else:
            lines += [f"DTSTART:{start:%Y%m%dT%H%M%S}", f"DTEND:{end:%Y%m%dT%H%M%S}"]
    else:  # TBA / TBD: all-day event
        lines += [f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}"]
    lines += [
        f"SUMMARY:{_escape(summary)}",
        f"LOCATION:{_escape(game.get('location', ''))}",
        f"DESCRIPTION:{_escape(chr(10).join(details))}",
        f"URL:{sport['schedule_url']}",
        "TRANSP:TRANSPARENT",  # don't mark you as busy
        "END:VEVENT",
    ]
    return lines


def _calendar(name: str, events: list[str]) -> str:
    head = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//uvm-athletics-dashboard//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(name)}",
        "X-WR-TIMEZONE:America/New_York",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
    ]
    return "\r\n".join(_fold(l) for l in head + events + ["END:VCALENDAR"]) + "\r\n"


def write_calendars(sports: list[dict], out_dir: Path) -> int:
    """Write one .ics per sport plus all.ics. Returns the number of files written."""
    out_dir.mkdir(exist_ok=True)
    stamp = _fmt_utc(datetime.now(timezone.utc))
    every: list[str] = []
    written = 0
    for sport in sports:
        games = [g for g in sport.get("games", []) if g.get("date")]
        if sport.get("error") or not games:
            continue
        events = [line for g in games for line in _event_lines(sport, g, stamp)]
        every += events
        (out_dir / f"{sport['slug']}.ics").write_text(_calendar(f"UVM {sport['name']}", events),
                                                      encoding="utf-8", newline="")
        written += 1
    (out_dir / "all.ics").write_text(_calendar("UVM Athletics", every), encoding="utf-8", newline="")
    return written + 1
