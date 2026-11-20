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
| `dashboard_template.html` | Page layout, styling and the JavaScript that renders the data. Edit this to change the look. |
| `dashboard.html` | Generated output — open in a browser. |
| `data.json` | Generated raw data, handy for debugging or other uses. |
| `.cache/` | Cached downloads (safe to delete). |

## Daily refresh on GitHub

`.github/workflows/refresh.yml` rebuilds the dashboard every day at 11:00 UTC
(6 a.m. EST / 7 a.m. EDT) and publishes it with GitHub Pages. It also runs on every push
to `main`, and you can trigger it by hand from the repo's **Actions** tab.

One-time setup: push this folder to a GitHub repo, then in **Settings → Pages** set
**Source** to **GitHub Actions**. Pages on a private repo needs a paid GitHub plan.

## Favorites and order

Use **⚙︎ Customize** on the dashboard to star teams and reorder them. Favorites come
first, then teams in season, then teams whose season is over. Settings are saved in
each browser, so a phone and a laptop each keep their own.

## Data sources

- `uvmathletics.com/sports/<sport>/schedule` and `/services/schedule_txt.ashx?schedule=<id>`
- `uvmathletics.com/rss.aspx`
- `americaeast.com/standings.aspx?path=<sport>`
- `hockeyeastonline.com/{men,women}/standings/index.php`

Scores are shown as the site lists them (winner's score first). Gold tags are team finishes
at meets (cross country, track, swimming invitationals, skiing). Scraping can break if these
sites change their page layout; the parsers are small and isolated so fixes stay quick.
