#!/usr/bin/env python3
"""Lineup optimizer (yellow mode): pull Yahoo's starters page for our team,
value each player, propose the optimal 9, compare vs current, print a
Telegram-ready card. Proposes only — the agent clicks after your OK.

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

FLEX_OK = ('RB', 'WR', 'TE')


def proj_from_cell(cell):
    """Yahoo's weekly projection, if the page shows one (usually appears ~Fri)."""
    m = re.search(r'(-?\d+(?:\.\d+)?)\s*proj', cell, re.I)
    return float(m.group(1)) if m else None


def pos_from_cell(cell):
    m = re.search(r'\b[A-Z]{2,3}\s*-\s*(QB|RB|WR|TE|K|DEF|DT|DL|LB|DB)\b', cell)
    if m:
        return m.group(1)
    m = re.search(r'\b(Was|Be)\s*-\s*(QB|RB|WR|TE|K|DEF)\b', cell)  # traded players
    if m:
        return m.group(2)
    return None


def season_weekly():
    """Fallback value: season PPR / 17 from the draft pool; K/DEF constants."""
    vals = {}
    try:
        pool = json.load(open(os.path.join(os.path.dirname(BASE),
                                           'draft-engine', 'data', 'draft_pool.json')))
        vals = {p['name']: p['projected_pts'] / 17.0 for p in pool}
    except OSError:
        pass
    vals.setdefault('Ka\u2019imi Fairbairn', 8.5)
    vals.setdefault("Ka'imi Fairbairn", 8.5)
    vals.setdefault('Eagles', 8.0)
    return vals


def load_draft_positions():
    path = os.path.join(BASE, 'scrape', 'draft_full.json')
    try:
        d = json.load(open(path))
        return {p['player']: p['pos'] for p in d['picks']}
    except OSError:
        return {}


def plan_lineup(players):
    chosen, used = [], set()

    def take(n, label, eligible):
        cand = sorted([p for p in players if p['pid'] not in used and p['pos'] in eligible],
                      key=lambda x: -x['proj'])[:n]
        for c in cand:
            used.add(c['pid'])
            chosen.append((label, c))

    take(1, 'QB', ('QB',))
    take(2, 'RB', ('RB',))
    take(2, 'WR', ('WR',))
    take(1, 'TE', ('TE',))
    take(1, 'W/R/T', FLEX_OK)
    take(1, 'K', ('K',))
    take(1, 'DEF', ('DEF',))
    return chosen, [p for p in players if p['pid'] not in used]


def main():
    cfg = load_config()
    launch_headless()
    base = f"https://football.fantasysports.yahoo.com/f1/{cfg['league_id']}/{cfg.get('team_id', 4)}"
    r = subprocess.run([BUN, EVAL, base + '/starters', JS, OUT],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0 or not os.path.exists(OUT):
        sys.exit(f'fetch failed: {r.stderr[:200]}')
    data = json.load(open(OUT))
    if 'error' in data:
        sys.exit(data['error'])
    draft_pos = load_draft_positions()
    weekly = season_weekly()
    players, used_fallback = [], 0
    for p in data['rows']:
        proj = proj_from_cell(p['cell'])
        if proj is None:
            proj = weekly.get(p['name'], 0.0)
            used_fallback += 1
        pos = (pos_from_cell(p['cell']) or draft_pos.get(p['name'])
               or {'W/R/T': 'FLEX', 'DEF': 'DEF', 'K': 'K'}.get(p['slot'], p['slot']))
        players.append({**p, 'proj': proj, 'pos': pos})
    current = {p['pid']: p['slot'] for p in players if p['is_start']}
    chosen, bench = plan_lineup(players)
    chosen_ids = {p['pid'] for _, p in chosen}

    src = "Yahoo weekly projections" if not used_fallback else \
        f"season-avg/week fallback ({used_fallback}/15)"
    L = ['🏈 LINEUP — Straight to Jail', f'   value source: {src}', '─' * 46]
    ups, downs = [], []
    for slot, p in chosen:
        mark = f" [{p['injury'][0]}]" if p['injury'] else ''
        star = ''
        if current.get(p['pid']) is None:
            star = '  ⬆ START'
            ups.append(p)
        L.append(f"  {slot:<6}{p['name']:<24}{p['proj']:>5.1f}{mark}{star}")
    L.append('─' * 46)
    L.append('  BN: ' + ', '.join(f"{p['name']} ({p['proj']:.1f})" for p in
                                  sorted(bench, key=lambda x: -x['proj'])))
    L.append('─' * 46)
    L.append(f"  proj total: {sum(p['proj'] for _, p in chosen):.1f}")
    for p in players:
        if p['is_start'] and p['pid'] not in chosen_ids:
            downs.append(p)
    if ups or downs:
        L.append('  🔁 PROPOSED SWAPS:')
        for u in ups:
            L.append(f"     IN  {u['name']} ({u['proj']:.1f})")
        for d in sorted(downs, key=lambda x: -x['proj']):
            L.append(f"     OUT {d['name']} ({d['proj']:.1f})")
        L.append('  reply ✅ to have the agent submit, or name your own')
    else:
        L.append('  ✅ current lineup already optimal — no action needed')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
