#!/usr/bin/env python3
"""
Rebuild data/draft_pool.json from:
  1. FantasyPros consensus draft rankings (ECR, tier, pos_rank, owned%) — scraped live
  2. ffdraft.app (jjti/ff) 2026 season projections — ESPN+CBS+NFL average, re-scored PPR
  3. Local sleeper_players.json — real sleeper IDs for name matches

Usage: python3 scripts/update_pool.py [--out data/draft_pool_2026.json]
"""
import json, re, csv, sys, os, argparse, urllib.request
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'}

def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', 'replace')

def extract_js_var(html, name):
    m = re.search(r'var\s+' + name + r'\s*=\s*', html)
    if not m:
        return None
    i = m.end()
    oc = html[i]; cc = {'{': '}', '[': ']'}[oc]
    depth = 0; in_str = False; esc = False
    for j in range(i, len(html)):
        c = html[j]
        if in_str:
            if esc: esc = False
            elif c == '\\': esc = True
            elif c == '"': in_str = False
        else:
            if c == '"': in_str = True
            elif c == oc: depth += 1
            elif c == cc:
                depth -= 1
                if depth == 0:
                    return json.loads(html[i:j+1])
    return None

SUFFIX = {'jr': '', 'sr': '', 'ii': '', 'iii': '', 'iv': '', 'v': ''}
def strip_glued(t):
    for s in ('jr', 'sr', 'iii', 'ii', 'iv'):  # 'v' skipped: too many real names end in v
        if t.endswith(s) and len(t) > len(s) + 2:
            return t[:-len(s)]
    return t
def norm(s):
    s = s.lower()
    s = s.split('(')[0]                      # drop "(Bye 6)" style suffixes
    s = re.sub(r"\u2019|'", '', s)           # apostrophes: Ja'Marr
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    toks = [strip_glued(t) for t in s.split() if t not in SUFFIX]
    return ''.join(toks)

def short(s):
    """last-name + first initial, for fuzzy fallback"""
    parts = norm(s).split()
    return parts[-1] + (parts[0][0] if parts else '')

# --- 1. FantasyPros consensus ECR ---
def load_fp():
    html = fetch('https://www.fantasypros.com/nfl/rankings/consensus-cheatsheets.php')
    ecr = extract_js_var(html, 'ecrData')
    if not ecr:
        raise RuntimeError('ecrData not found — page structure changed')
    print(f"[fp] consensus scraped: {ecr['count']} players, {ecr['total_experts']} experts, updated {ecr['last_updated']}")
    return {p['player_filename']: p for p in ecr['players']}, ecr

# --- 2. ffdraft 2026 projections (PPR re-scored) ---
def load_proj():
    """Union ffdraft's two projection vintages: app JSON (veterans, daily) + repo CSV (rookies).
    NOTE: both files' 'ppr' columns are RANKS — points are always recomputed from raw stats."""
    out = {}

    def add(name, team, g, bye):
        n = norm(name)
        if not n:
            return
        pts = (float(g('passYds') or g('pass_yds') or 0)/25 + float(g('passTds') or g('pass_tds') or 0)*4
               - float(g('passInts') or g('pass_ints') or 0)*2 + float(g('twoPts') or g('two_pts') or 0)*2
               + float(g('rushYds') or g('rush_yds') or 0)/10 + float(g('rushTds') or g('rush_tds') or 0)*6
               + float(g('receptionYds') or g('reception_yds') or 0)/10 + float(g('receptionTds') or g('reception_tds') or 0)*6
               + float(g('receptions') or 0)
               - float(g('fumbles') or 0)*2
               + float(g('dfTds') or g('df_tds') or 0)*6 + float(g('dfSacks') or g('df_sacks') or 0)
               + float(g('dfInts') or g('df_ints') or 0) + float(g('dfFumbles') or g('df_fumbles') or 0)
               + float(g('dfSafeties') or g('df_safeties') or 0)*2
               - float(g('dfPointsAllowedPerGame') or g('df_points_allowed_per_game') or 0)
               + float(g('kickExtraPoints') or g('kick_extra_points') or 0)
               + float(g('kick019') or g('kick_0_19') or 0)*3 + float(g('kick2029') or g('kick_20_29') or 0)*4
               + float(g('kick3039') or g('kick_30_39') or 0)*5 + float(g('kick4049') or g('kick_40_49') or 0)*6
               + float(g('kick50') or g('kick_50') or 0)*7)
        if n not in out or pts > out[n]['ppr']:
            out[n] = {'ppr': round(pts, 1), 'team': team, 'bye': bye}

    try:
        d = json.loads(fetch('https://raw.githubusercontent.com/jjti/ff/main/app/public/projections.json'))
        for r in d['data']:
            if r['pos'] in ('QB', 'RB', 'WR', 'TE'):
                add(r['name'], r['team'], lambda k, _r=r: _r.get(k), r.get('bye'))
        print(f"[ffdraft] app JSON: {len(out)} players")
    except Exception as e:
        print(f"[ffdraft] app JSON failed: {e}")

    try:
        csv_text = fetch('https://raw.githubusercontent.com/jjti/ff/main/data/processed/Projections-2026.csv')
        before = len(out)
        for r in csv.DictReader(csv_text.splitlines()):
            if r['pos'] in ('QB', 'RB', 'WR', 'TE'):
                add(r['name'], r['team'], lambda k, _r=r: _r.get(k), r.get('bye'))
        print(f"[ffdraft] repo CSV added {len(out)-before} more")
    except Exception as e:
        print(f"[ffdraft] repo CSV failed: {e}")

    print(f"[ffdraft] total projections: {len(out)} players")
    return out

# --- 3. sleeper id map ---
def load_sleeper():
    path = os.path.join(ROOT, 'data', 'sleeper_players.json')
    if not os.path.exists(path):
        return {}
    d = json.load(open(path))
    m = {}
    for pid, p in d.items():
        name = p.get('full_name') or ''
        if name and p.get('position') in ('QB', 'RB', 'WR', 'TE'):
            m[norm(name)] = pid
    print(f"[sleeper] id map: {len(m)} skill players")
    return m

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'data', 'draft_pool.json'))
    ap.add_argument('--top', type=int, default=200, help='max skill players to keep')
    ap.add_argument('--min-owned', type=float, default=0.0)
    args = ap.parse_args()

    fp_by_file, meta = load_fp()
    proj = load_proj()
    slp = load_sleeper()

    # build norm-name index of fp with position to avoid collisions
    fp_index = {}
    for fn, p in fp_by_file.items():
        pos = p['player_position_id']
        if pos not in ('QB', 'RB', 'WR', 'TE'):
            continue
        if p['player_owned_avg'] < args.min_owned:
            continue
        key = (norm(p['player_name']), pos)
        fp_index.setdefault(key, p)

    by_short = {}
    for (n, pos), p in fp_index.items():
        by_short.setdefault((short(n), pos), p)

    players, unmatched = [], []
    for key, p in sorted(fp_index.items(), key=lambda kv: kv[1]['rank_ecr']):
        n, pos = key
        pr = proj.get(n)
        if pr is None and p['player_name'].lower() in ('emeka egbukam',):
            pr = proj.get(norm('Emeka Egbuka'))
        if pr is None:
            pr = proj.get(norm(p['player_name'].replace('.', '').replace('-', ' ')))
        if pr is None:
            unmatched.append(f"{p['player_name']} ({p['pos_rank']})")
            continue
        # prefer ffdraft team (live) over FP team
        team = pr['team'] if pr['team'] and pr['team'] not in ('FA', 'NA', '') else p['player_team_id']
        players.append({
            'rank': p['rank_ecr'],
            'name': p['player_name'],
            'position': pos,
            'team': team,
            'projected_pts': pr['ppr'],
            'tier': int(p.get('tier') or 0),
            'sleeper_id': slp.get(n, f"fp_{p['player_id']}"),
            'ecr_rank': p['rank_ecr'],
            'pos_rank': p['pos_rank'],
            'rank_min': int(p['rank_min']),
            'rank_max': int(p['rank_max']),
            'rank_std': round(float(p['rank_std']), 2),
            'owned_pct': p['player_owned_avg'],
            'bye': int(float(p['player_bye_week'] or 0)),
        })

    print(f"[join] matched {len(players)} | FP-unmatched {len(unmatched)}")
    if unmatched:
        print('  missing projections for:', ', '.join(unmatched[:15]))

    players.sort(key=lambda x: x['ecr_rank'])
    players = players[:args.top]
    for i, pl in enumerate(players, 1):
        pl['rank'] = i

    counts = Counter(pl['position'] for pl in players)
    print(f"[pool] keeping {len(players)}: {dict(counts)}")
    json.dump(players, open(args.out, 'w'), indent=2)
    print(f"[pool] wrote {args.out}")
    print('\nTop 10:')
    for pl in players[:10]:
        print(f"  {pl['ecr_rank']:>3}. {pl['name']:<22} {pl['pos_rank']:<5} PPR {pl['projected_pts']:>6.1f}  owned {pl['owned_pct']}%")

if __name__ == '__main__':
    main()
