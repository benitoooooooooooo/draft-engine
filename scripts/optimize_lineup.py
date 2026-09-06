#!/usr/bin/env python3
"""Lineup optimizer (yellow mode): pulls Yahoo's own weekly projections for
our 15 players, proposes the optimal 9, compares against Yahoo's current
starters, prints a Telegram-ready card. Proposes only — the agent clicks
after your OK.

Usage: .venv/bin/python scripts/optimize_lineup.py
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yahoo_session import BASE, load_config, launch_headless

BUN = os.path.expanduser('~/.bun/bin/bun')
EVAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fetch_cdp_eval.js')
OUT = os.path.join(BASE, 'week_projections.json')

# Pull our team's row set with: slot, name, pid, injury, and full cell text
JS = '''
(() => {
  const tables = [...document.querySelectorAll('table')];
  const ours = tables.find(t => t.innerText.includes('Jayden Daniels') &&
                                t.innerText.includes('Christian McCaffrey'));
  if (!ours) return JSON.stringify({error: 'team table not found'});
  const rows = [];
  [...ours.querySelectorAll('tr')].forEach(tr => {
    const cells = [...tr.querySelectorAll('td')];
    if (cells.length < 2) return;
    const slot = cells[0].innerText.trim().toUpperCase();
    const nameEl = cells[1].querySelector('a.name');
    if (!nameEl) return;
    const inj = cells[1].querySelector('.F-injury span[title]');
    rows.push({slot, name: nameEl.innerText.trim(),
               pid: nameEl.getAttribute('data-ys-playerid'),
               injury: inj ? inj.getAttribute('title') : '',
               cell: cells[1].innerText.replace(/\\s+/g, ' ').slice(0, 150),
               is_start: !/^(BN|IR)$/.test(slot)});
  });
  return JSON.stringify({rows});
})()
'''

STARTERS = {'QB': 1, 'RB': 2, 'WR': 2, 'TE': 1, 'FLEX': 1, 'K': 1, 'DEF': 1}
FLEX_OK = ('RB', 'WR', 'TE')


def proj_from_cell(cell):
    m = re.search(r'(-?\d+(?:\.\d+)?)\s*proj', cell, re.I)
    return float(m.group(1)) if m else 0.0


def optimize(rows):
    players = []
    for r in rows:
        players.append({**r, 'proj': proj_from_cell(r['cell'])})
    by_slot = {}
    for p in players:
        s = {'W/R/T': 'FLEX', 'DEF': 'DEF', 'K': 'K'}.get(p['slot'], p['slot'])
        p['eligible'] = [s] if s in ('K', 'DEF') else (
            ['QB'] if s == 'QB' else (['RB', 'WR', 'TE', 'FLEX'] if s in FLEX_OK else
                                      ['RB', 'WR', 'TE', 'FLEX']))
        by_slot.setdefault(p['slot'], []).append(p)
    # greedy: fill by slot requirement; player eligibility from their REAL position
    # BN rows still hold their underlying position via name matching to team draft?
    # Simpler: BN eligible for FLEX if RB/WR/TE per their draft pos -> we know from
    # Yahoo: BN players list their pos in cell? no. Use season roster positions:
    return players


POS_FROM_DRAFT = {}  # pid -> RB/WR/TE/QB/K/DEF (filled from draft_full.json + settings)


def load_positions():
    """Map player names to positions via the draft record (authoritative)."""
    path = os.path.join(BASE, 'scrape', 'draft_full.json')
    try:
        d = json.load(open(path))
        return {p['player']: p['pos'] for p in d['picks']}
    except OSError:
        return {}


def best_lineup(players, real_pos):
    for p in players:
        if p['slot'] in ('BN', 'IR'):
            p['pos'] = real_pos.get(p['name'], '?')
        else:
            p['pos'] = {'W/R/T': 'FLEX', 'DEF': 'DEF'}.get(p['slot'], p['slot'])
    chosen = []
    used = set()
    def take(n, predicate, label):
        cand = sorted([p for p in players if p['pid'] not in used and predicate(p)],
                      key=lambda x: -x['proj'])[:n]
        for c in cand:
            used.add(c['pid'])
            chosen.append((label, c))
        return len(cand) == n
    take(STARTERS['QB'], lambda p: p['pos'] == 'QB', 'QB')
    take(STARTERS['RB'], lambda p: p['pos'] == 'RB', 'RB')
    take(STARTERS['WR'], lambda p: p['pos'] == 'WR', 'WR')
    take(STARTERS['TE'], lambda p: p['pos'] == 'TE', 'TE')
    flex_ok = take(STARTERS['FLEX'], lambda p: p['pos'] in FLEX_OK, 'W/R/T')
    take(STARTERS['K'], lambda p: p['pos'] == 'K', 'K')
    take(STARTERS['DEF'], lambda p: p['pos'] == 'DEF', 'DEF')
    return chosen, [p for p in players if p['pid'] not in used]


def main():
    cfg = load_config()
    launch_headless()
    base = f"https://football.fantasysports.yahoo.com/f1/{cfg['league_id']}/{cfg.get('team_id',4)}"
    r = subprocess.run([BUN, EVAL, base + '/starters', JS, OUT],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0 or not os.path.exists(OUT):
        sys.exit(f'fetch failed: {r.stderr[:200]}')
    data = json.load(open(OUT))
    if 'error' in data:
        sys.exit(data['error'])
    players = [{**p, 'proj': proj_from_cell(p['cell'])} for p in data['rows']]
    current = {p['pid']: p['slot'] for p in players if p['is_start']}
    real_pos = load_positions()
    chosen, bench = best_lineup(players, real_pos)
    chosen_ids = {c['pid'] for _, c in chosen}

    L = ['🏈 WEEK 1 LINEUP — Straight to Jail', '   (by Yahoo\'s own projections)', '─' * 44]
    ups = []
    for slot, p in chosen:
        mark = f" [{p['injury'][0]}]" if p['injury'] else ''
        was = current.get(p['pid'])
        star = '  ⬆ START' if was is None else ''
        if was is None:
            ups.append(p['name'])
        L.append(f"  {slot:<6}{p['name']:<24}{p['proj']:>5.1f}{mark}{star}")
    L.append('─' * 44)
    L.append('  BN: ' + ', '.join(f"{p['name']} ({p['proj']:.1f})" for p in
                                  sorted(bench, key=lambda x: -x['proj'])))
    total = sum(p['proj'] for _, p in chosen)
    L.append('─' * 44)
    L.append(f"  proj total: {total:.1f}")
    if ups:
        L.append(f"  🔁 PROPOSED CHANGE: start {' + '.join(ups)}")
        for name in ups:
            drop = max((p for p in bench), key=lambda x: x['proj'])
            L.append(f"     in: {name} ({[p for _,p in chosen if p['name']==name][0]['proj']:.1f})"
                     f"   out: {drop['name']} ({drop['proj']:.1f})")
    else:
        L.append('  ✅ Yahoo current lineup is already projection-optimal')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
