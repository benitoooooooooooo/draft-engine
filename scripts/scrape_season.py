#!/usr/bin/env python3
"""Scrape draft results + all team rosters from the authenticated session.
Output: ~/yahoo-bot/scrape/draft_results.json, rosters/<teamid>.html"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yahoo_session import load_config, BASE

BUN = os.path.expanduser('~/.bun/bin/bun')
FETCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fetch_cdp.js')
EVAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fetch_cdp_eval.js')
OUT = os.path.join(BASE, 'scrape')


def run(js_file, url, arg, wait='3000'):
    r = subprocess.run([BUN, js_file, url, arg, wait], capture_output=True,
                       text=True, timeout=120)
    if r.returncode != 0:
        print('ERR', url, r.stderr[:200])
    return r.stdout.strip()


def main():
    cfg = load_config()
    lid = cfg['league_id']
    base = f'https://football.fantasysports.yahoo.com/f1/{lid}'
    os.makedirs(os.path.join(OUT, 'rosters'), exist_ok=True)

    # 1. draft results (also gives manager/team mapping)
    run(FETCH, f'{base}/draft', os.path.join(OUT, 'draft_results.html'), '5000')
    html = open(os.path.join(OUT, 'draft_results.html')).read()
    print('draft page bytes:', len(html), '| BEEF:', 'BEEF' in html,
          '| McCaffrey:', 'McCaffrey' in html)

    # manager -> team id mapping from the page (team links near manager names)
    pairs = re.findall(r'f1/\d+/(\d+)"[^>]*>([^<]{2,40})<', html)
    print('team links found:', len(set(p[0] for p in pairs)))

    # 2. all 10 roster pages
    team_ids = sorted(set(p[0] for p in pairs if p[0].isdigit() and 1 <= int(p[0]) <= 10))
    for tid in team_ids:
        out = os.path.join(OUT, 'rosters', f'{tid}.html')
        run(FETCH, f'{base}/{tid}', out, '4000')
        try:
            sz = os.path.getsize(out)
            has = 'McCaffrey' if 'McCaffrey' in open(out).read() else ''
            print(f'roster {tid}: {sz}b {has}')
        except OSError:
            print(f'roster {tid}: MISSING')


if __name__ == '__main__':
    main()
