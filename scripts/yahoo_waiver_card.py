#!/usr/bin/env python3
"""WAIVER CARD (cron --no-agent on the mini). Lists the league wire ranked
by season-avg weekly value, flags coverage for our injured/questionable
starters. Proposes only; agent submits claims after user ✅."""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, '/Users/benbrackett/draft-engine/scripts')
from yahoo_session import load_config, launch_headless
from optimize_lineup import BUN, EVAL, JS, pos_from_cell, season_weekly, load_draft_positions
from weekly_values import lookup as weekly_lookup

WIRE_JS = """JSON.stringify([...document.querySelectorAll('table tr')].map(tr => {
  const tds = [...tr.querySelectorAll('td')];
  if (tds.length < 4) return null;
  const nameEl = tds[2].querySelector('a.name') || tds[2].querySelector('a');
  if (!nameEl) return null;
  const txt = tds[2].innerText.replace(/\\s+/g, ' ');
  return {name: nameEl.innerText.trim(),
          cell: txt.slice(0, 120),
          rostered: tds.length >= 6 ? tds[tds.length-2].innerText.trim().slice(0, 8) : '',
          start: tds.length >= 6 ? tds[tds.length-1].innerText.trim().slice(0, 8) : ''};
}).filter(Boolean).slice(0, 80))"""


def main():
    cfg = load_config()
    launch_headless()
    lid = cfg['league_id']
    # our injury situation first
    team_url = f"https://football.fantasysports.yahoo.com/f1/{lid}/4"
    me = json.loads(subprocess.run(
        [BUN, EVAL, team_url + '/starters', JS], capture_output=True,
        text=True, timeout=180).stdout.strip().splitlines()[-1])
    me = json.loads(me) if isinstance(me, str) else me
    injured = [(r['name'], r['injury'], r['slot']) for r in me['rows']
               if r['injury'] and r['is_start']]

    weekly, dpos = season_weekly(), load_draft_positions()
    wire = json.loads(subprocess.run(
        [BUN, EVAL, f'https://football.fantasysports.yahoo.com/f1/{lid}/players?status=A',
         WIRE_JS], capture_output=True, text=True, timeout=180)
        .stdout.strip().splitlines()[-1])
    wire = json.loads(wire) if isinstance(wire, str) else wire

    rows, graded = [], 0
    for p in wire:
        pos = pos_from_cell(p['cell']) or dpos.get(p['name'])
        wk = weekly_lookup(p['name'])
        if wk:
            val, grade, opp = wk[0], wk[1], wk[2]
            graded += 1
        else:
            val, grade, opp = weekly.get(p['name'], 0.0), '', ''
        if pos and val > 0:
            rows.append((p['name'], pos, val, grade, opp))
    rows.sort(key=lambda x: -x[2])
    seen, top = set(), []
    for name, pos, val, grade, opp in rows:
        if name not in seen:
            seen.add(name)
            top.append((name, pos, val, grade, opp))

    L = ['🌊 WEEKLY WAIVER SWEEP — Straight to Jail',
         '   matchup-aware weekly consensus (incl FTN)', '─' * 44]
    if injured:
        L.append('⚠ Our injuries: ' + ', '.join(f'{n} [{i}]' for n, i, _ in injured))
    L.append('Best on the wire (season-avg/week):')
    for name, pos, val, grade, opp in top[:12]:
        g = f"{grade:<2}" if grade else '  '
        o = opp[:8] if opp else ''
        L.append(f'  {pos:<4} {name:<26} {g}{o:<9} {val:>5.1f}')
    L.append('─' * 44)
    L.append('reply with names to claim (agent submits), or ✅ for top-2 by position need')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
