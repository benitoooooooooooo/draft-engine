#!/usr/bin/env python3
"""Weekly values layer: FantasyPros weekly consensus (aggregate of ~40
experts incl FTN, matchup-aware) via the DynastyProcess daily mirror.

Provides: weekly_values() -> {norm_name: {'r2p': float, 'grade': str,
'opp': str, 'pos': str}} and norm(name) for cross-source joins.
"""
import csv
import io
import re
import urllib.request

CSV_URL = ('https://raw.githubusercontent.com/dynastyprocess/data/master/'
           'files/fp_latest_weekly.csv')
TEAM_WORDS = {'Cardinals','Falcons','Ravens','Bills','Panthers','Bears',
              'Bengals','Browns','Cowboys','Broncos','Lions','Packers',
              'Texans','Colts','Jaguars','Commanders','Jets','Dolphins',
              'Patriots','Raiders','Saints','Giants','Bucs','Buccaneers',
              'Titans','Chiefs','Eagles','Rams','Ravens','49ers','Seahawks',
              'Steelers','Vikings','Cowboys'}


def norm(s):
    s = s.lower().replace('\u2019', "'")
    s = re.sub(r"['\.]", '', s)
    s = re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', '', s)
    return ' '.join(s.split())


def _load():
    req = urllib.request.Request(CSV_URL, headers={'User-Agent': 'Mozilla/5.0'})
    raw = urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace')
    rows = list(csv.DictReader(io.StringIO(raw)))
    out, by_team = {}, {}
    for r in rows:
        pos = r['pos']
        if pos not in ('QB', 'RB', 'WR', 'TE', 'K', 'DST', 'DEF'):
            continue  # skip IDP
        try:
            r2p = float(r['r2p_pts'])
        except (ValueError, KeyError):
            continue
        entry = {'r2p': r2p, 'grade': r.get('start_sit_grade', ''),
                 'opp': r.get('player_opponent', ''), 'pos': pos}
        name = r['player_name']
        out[norm(name)] = entry
        if pos in ('DST', 'DEF'):
            # store by the team nickname alone too ("Philadelphia Eagles" -> "eagles")
            toks = norm(name).split()
            if toks:
                by_team[toks[-1]] = entry
    return out, by_team


_CACHE = None


def weekly_values():
    global _CACHE
    if _CACHE is None:
        _CACHE = _load()
    return _CACHE


def lookup(name, pos=None):
    """Returns (r2p, grade, opp) or None. Handles DEF-by-city/team names."""
    values, by_team = weekly_values()
    n = norm(name)
    if n in values:
        v = values[n]
        return v['r2p'], v['grade'], v['opp']
    # defense: 'Eagles' matches 'Philadelphia Eagles'
    toks = n.split()
    for t in toks:
        if t in by_team:
            v = by_team[t]
            return v['r2p'], v['grade'], v['opp']
    # last-name fuzzy tail for Yahoo suffix quirks
    exact = [k for k in values if k.endswith(toks[-1]) and len(toks) > 1
             and k.startswith(toks[0])]
    if len(exact) == 1:
        v = values[exact[0]]
        return v['r2p'], v['grade'], v['opp']
    return None


if __name__ == '__main__':
    v, bt = weekly_values()
    print(f'weekly consensus: {len(v)} players, {len(bt)} DSTs')
    for probe in ['Christian McCaffrey', "De'Von Achane", 'Jayden Daniels',
                  'Trey McBride', 'Eagles', 'Ka\u2019imi Fairbairn']:
        print(f'  {probe:<22}', lookup(probe))
