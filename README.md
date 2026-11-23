# UVM Athletics Dashboard

A personal dashboard of University of Vermont scores, results, standings and news.
Pure Python 3 standard library — nothing to install.

```bash
python3 uvm_dashboard.py --open      # fetch (cached 30 min), build dashboard.html, open it
python3 uvm_dashboard.py --refresh   # ignore the cache
python3 hockey_east.py               # print Hockey East standings on their own
```

## Files

| File | What it does |
|---|---|
| `uvm_dashboard.py` | Main scraper and builder. Schedules/scores from UVM's Sidearm text export, meet placements and recap/results/box-score links from the schedule pages, news from the RSS feed, America East standings. |
| `hockey_east.py` | Separate scraper for men's and women's Hockey East standings (hockeyeastonline.com). |
| `rankings.py` | UVM's national rank per sport from the polls on ncaa.com ("#12", "RV" for receiving votes, or unranked). No women's hockey poll there. Opponents' ranks (gold "#9") and tournament seeds ("(2)") come from UVM's own schedule pages. |
| `dashboard_template.html` | Page layout, styling and the JavaScript that renders the data. Edit this to change the look. |
| `calendars.py` | Writes subscribable calendars to `calendars/` on every build: one `.ics` per team plus `all.ics`. Times are converted from Eastern, TBA games become all-day events, and each event lists where to watch plus links. Subscribe from a team's popup (or the all-teams link above the footer). |
| `manifest.webmanifest`, `sw.js`, `icons/` | Home-screen app support: name, icon and full-screen mode, plus a service worker so the installed app opens offline with the last build. `icons/icon.svg` is the source for the PNGs. |
| `dashboard.html` | Generated output — open in a browser. |
| `data.json` | Generated raw data, handy for debugging or other uses. |
| `calendars/` | Generated `.ics` calendar files (published with the site). |
| `.cache/` | Cached downloads (safe to delete). |

## Automatic refresh on GitHub

`.github/workflows/refresh.yml` rebuilds the dashboard and publishes it with GitHub Pages:

- **1:37 a.m. Eastern, year-round** (main build, after the night's games are final).
  GitHub's scheduler only uses UTC, so this is scheduled at both 05:37 and 06:37 UTC and a
  small "gate" job keeps whichever one is 1:37 a.m. in New York that day (the other shows as
  a skipped run).
- **Backup at 15:41 UTC** (10:41 a.m. EST / 11:41 a.m. EDT), in case the main build was late
  or dropped.
- On every push to `main`, and by hand from the repo's **Actions** tab.

GitHub's free scheduler starts runs late when its queue is busy. The original 5 a.m. slot
(09:00/10:00 UTC, on the hour) ran 7–8 hours late every day, so the main build moved to an
off-peak time and an odd minute. The "Updated" time at the top of the dashboard shows when the
last build actually ran. If it keeps showing late times, the fallback is an outside scheduler
(e.g. cron-job.org) triggering the workflow at an exact time.

One-time setup: push this folder to a GitHub repo, then in **Settings → Pages** set
**Source** to **GitHub Actions**. Pages on a private repo needs a paid GitHub plan.

## Favorites and order

Use **⚙︎ Customize** on the dashboard to star favorites, hide teams you don't follow,
reorder teams, and turn **Show out-of-season teams** on or off (favorites always show).
Favorites come first, then teams in season, then teams whose season is over. Hidden teams
disappear everywhere: buttons, cards, results, upcoming games and news. Settings are saved
in each browser, so a phone and a laptop each keep their own.

## Data sources

- `uvmathletics.com/sports/<sport>/schedule` and `/services/schedule_txt.ashx?schedule=<id>`
- `uvmathletics.com/rss.aspx`
- `americaeast.com/standings.aspx?path=<sport>`
- `hockeyeastonline.com/{men,women}/standings/index.php`
- `ncaa.com/rankings/<sport>/d1` (USCHO.com, AP, United Soccer Coaches, and other polls)

Scores are shown as the site lists them (winner's score first). Gold tags are team finishes
at meets (cross country, track, swimming invitationals, skiing). Scraping can break if these
sites change their page layout; the parsers are small and isolated so fixes stay quick.
