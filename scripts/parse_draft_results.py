#!/usr/bin/env python3
"""Parse draft_results.html into draft_results.json (full 150 picks with teams)."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yahoo_session import BASE

SRC = os.path.join(BASE, 'scrape', 'draft_results.html')


def main():
    html = open(SRC).read()
    # rows: <td class="first">1.</td><td class="pick">(5)</td><td class="player"...><a...>NAME</a></td><td class="position...">RB</td>
    row_pat = re.compile(
        r'<td class="first">\s*(\d+)\.\s*</td>\s*'
        r'<td class="pick">\s*\((\d+)\)\s*</td>\s*'
        r'<td class="player"[^>]*>.*?>([^<]+)</a>.*?'
        r'<td class="position[^>]*>\s*([A-Z/@\. ]+?)\s*(?:<|\()',
        re.S)
    picks = []
    for m in row_pat.finditer(html):
        rnd, pick, name, pos = m.groups()
        picks.append({'round': int(rnd), 'pick': int(pick),
                      'name': name.strip(), 'pos': pos.strip()})
    picks.sort(key=lambda p: p['pick'])
    print(f'parsed {len(picks)} picks')
    # team name mapping: look for team headers like <h2 class="Grid-u">NAME</h2> near links /f1/968508/<tid>
    team_pat = re.compile(r'href="/f1/968508/(\d{1,2})"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{3,40}?)\s*</', re.S)
    tm = {}
    for m in team_pat.finditer(html):
        tid, name = m.groups()
        name = name.strip()
        if 1 <= int(tid) <= 10 and name and name not in ('View All',):
            tm.setdefault(tid, name)
    print('team names found:', len(tm))
    for k in sorted(tm, key=int):
        print(f'  {k}: {tm[k]}')
    out = os.path.join(BASE, 'scrape', 'draft_results.json')
    json.dump({'picks': picks, 'teams': tm}, open(out, 'w'), indent=2)
    print('wrote', out)
    if picks:
        print('sample:', picks[:3])
        print('pick 16:', [p for p in picks if p['pick'] == 16])


if __name__ == '__main__':
    main()
