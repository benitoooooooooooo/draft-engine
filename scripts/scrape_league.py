#!/usr/bin/env python3
"""
Yahoo league scraper (yellow-mode phase 1/2 data layer).

Drives the persistent logged-in Chrome (scripts/yahoo_session.py) over CDP,
pulls league pages, and dumps both raw HTML (debugging) and extracted data
for the season engine.

Once logged in, run:  .venv/bin/python scripts/scrape_league.py --pages teams,standings,calendar
Then teach me the page structures: parsed output lands in ~/yahoo-bot/scrape/*.json
"""
import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yahoo_session import load_config, league_page, CDP_PORT, BASE, ensure_dirs

PAGES = {
    'teams':      '/teams',
    'standings':  '/standings',
    'schedule':   '/schedule',
    'playoffs':   '/playoffs',
    'percentowned': '/percentowned',
    'waivers':    '/waivers',
    'statistics': '/statistics',
}


def fetch_headless(url, out_path, wait=2):
    """Drive the persistent CDP Chrome via bun + fetch_cdp.js (websocket-free python)."""
    import subprocess
    from yahoo_session import launch_headless
    launch_headless()  # idempotent
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fetch_cdp.js')
    bun = os.path.expanduser('~/.bun/bin/bun')
    r = subprocess.run([bun, script, url, out_path, str(int(wait * 1000))],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f'fetch_cdp failed: {r.stderr[:300]}')
    with open(out_path) as f:
        return f.read()


def wall_check(html):
    title = re.search(r'<title>([^<]*)', html)
    t = title.group(1) if title else ''
    signed_in = ('Sign in' not in t and 'log in' not in t.lower()[:60])
    return signed_in, t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pages', default='teams')
    ap.add_argument('--outdir', default=os.path.join(BASE, 'scrape'))
    args = ap.parse_args()
    cfg = load_config()
    os.makedirs(args.outdir, exist_ok=True)
    lid = cfg['league_id']
    base = f"https://football.fantasysports.yahoo.com/f1/{lid}"
    for page in args.pages.split(','):
        path = PAGES.get(page.strip())
        if not path:
            print(f'skip unknown page {page}')
            continue
        url = base + path
        out = os.path.join(args.outdir, f'{page.strip()}.html')
        html = fetch_headless(url, out)
        ok, title = wall_check(html)
        size = len(html)
        status = 'OK' if ok else 'WALL/LOGIN NEEDED'
        print(f'{page:<14} {size:>8}b  [{status}]  title="{title[:60]}"')


if __name__ == '__main__':
    main()
