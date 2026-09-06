#!/usr/bin/env python3
"""Parse Yahoo f1 teams page (dumped via scrape_league.py) into structured
rosters. Yahoo renders rosters as team sections with player links
/f1/<lid>/players/<pid>/ and position tags. We extract what the DOM shows."""
import json
import os
import re
import sys
from collections import defaultdict

SRC = os.path.expanduser('~/yahoo-bot/scrape/teams.html')


def parse(html):
    teams = {}
    # Team blocks: manager names appear as links to team pages /f1/968508/<teamid>
    # Roster players appear as /f1/968508/players/<pid>/<slug> with (POS) labels
    # Simple approach: split on manager-link sections
    team_pat = re.compile(
        r'href="https://football\.fantasysports\.yahoo\.com/f1/968508/(\d+)"[^>]*>([^<]{2,30})</a>',
        re.S)
    player_pat = re.compile(
        r'/f1/968508/players/(\d+)/[a-z\-]+[^>]*>\s*(.*?)\s*</a>', re.S)
    pos_pat = re.compile(r'\((QB|RB|WR|TE|K|DEF|FLEX|BN|IL|OP|DL|LB|DB|IDP|IR)\)', re.I)

    # segment html by team anchors
    matches = list(team_pat.finditer(html))
    # dedupe team ids keeping order
    seen = []
    for m in matches:
        if m.group(1) not in [s[0] for s in seen]:
            seen.append((m.group(1), m.group(2).strip(), m.start()))
    for i, (tid, name, start) in enumerate(seen):
        end = seen[i + 1][2] if i + 1 < len(seen) else len(html)
        seg = html[start:end]
        players = []
        for pm in player_pat.finditer(seg):
            label = re.sub(r'<[^>]+>', ' ', pm.group(2))
            label = re.sub(r'\s+', ' ', label).strip()
            posm = pos_pat.search(label)
            pname = pos_pat.sub('', label).split(' - ')[0].strip()
            if pname and len(pname) > 1:
                players.append({'name': pname.title() if pname.islower() else pname,
                                'pos': posm.group(1).upper() if posm else '?'})
        teams[name] = {'team_id': tid, 'players': players}
    return teams


if __name__ == '__main__':
    html = open(SRC).read()
    print('html size:', len(html))
    teams = parse(html)
    for name, t in list(teams.items()):
        pos_counts = defaultdict(int)
        for p in t['players']:
            pos_counts[p['pos']] += 1
        print(f"{name:<20} ({len(t['players']):>2} players) {dict(pos_counts)}")
    out = os.path.join(os.path.dirname(SRC), 'rosters.json')
    json.dump(teams, open(out, 'w'), indent=2)
    print('wrote', out)
