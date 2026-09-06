#!/usr/bin/env python3
"""Parse draft_all.html -> full 150-pick draft with team names + Ben's roster."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yahoo_session import BASE

SRC = os.path.join(BASE, 'scrape', 'draft_all.html')
ROW = re.compile(
    r'<td class="first">\s*(\d+)\.\s*</td>\s*'
    r'<td class="player[^"]*">\s*<a[^>]+>([^<]+)</a>\s*'
    r'<span[^>]*>\(([^)]+?)\s*-\s*([A-Za-z/@.]+)\)\s*</span>\s*</td>\s*'
    r'<td class="last[^"]*"[^>]*title="([^"]+)"',
    re.S)


def main():
    html = open(SRC).read()
    rows = []
    for i, m in enumerate(ROW.finditer(html)):
        pick, player, nflteam, pos, team = m.groups()
        rows.append({'round': i // 10 + 1, 'pick': int(pick), 'overall': i + 1,
                     'player': player.strip(), 'nfl_team': nflteam.strip().upper(),
                     'pos': pos.strip().upper(), 'team': team.strip()})
    # rows may be duplicated per sort view; dedupe by (player, team)
    seen, picks = set(), []
    for r in rows:
        key = (r['player'], r['team'])
        if key not in seen:
            seen.add(key)
            picks.append(r)
    print(f'unique picks parsed: {len(picks)}')
    teams = sorted(set(r['team'] for r in picks))
    print(f'{len(teams)} teams:', teams)
    out = os.path.join(BASE, 'scrape', 'draft_full.json')
    json.dump({'teams': teams, 'picks': picks}, open(out, 'w'), indent=2)
    from collections import defaultdict
    by_team = defaultdict(list)
    for r in picks:
        by_team[r['team']].append(r)
    for t in teams:
        rs = by_team[t]
        print(f"\n{t} ({len(rs)}):")
        for r in sorted(rs, key=lambda x: (x['round'], x['pick_in_round']))[:15]:
            print(f"  R{r['round']:<2} {r['player']:<24} {r['pos']:<3} {r['nfl_team']}")
        if len(rs) > 15:
            print(f"  ...+{len(rs)-15}")


if __name__ == '__main__':
    main()
