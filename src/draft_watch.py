#!/usr/bin/env python3
"""
Draft Watch — read-only companion to the live CLI draft.

Reconstructs draft state from draft_state.json (written by the CLI on every
pick) and answers questions: recommendations, top available, run detection,
need analysis. Designed to be called by the Hermes agent while the operator
is drafting in their own terminal — no coupling to the running process.

Usage:
  python3 src/draft_watch.py status            # scoreboard + on the clock
  python3 src/draft_watch.py recs [n]          # my next-pick recommendations
  python3 src/draft_watch.py top <pos> [n]     # top available at position
  python3 src/draft_watch.py run               # positional run detection
  python3 src/draft_watch.py need <pos>        # positional need + depth left
  python3 src/draft_watch.py compare A B       # head-to-head of two available players
  python3 src/draft_watch.py json              # raw engine view (for agent parsing)

All commands accept --team N (1-based); default = team from draft_state.json.
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import Player, DraftConfig, DraftState, ValuationEngine, load_draft_pool

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(ROOT, 'draft_state.json')
POOL_PATHS = [
    os.path.join(ROOT, 'data', 'draft_pool_2026.json'),
    os.path.join(ROOT, 'data', 'draft_pool.json'),
]


def load_pool():
    for p in POOL_PATHS:
        if os.path.exists(p):
            try:
                pool = load_draft_pool(p)
                if pool:
                    return pool, p
            except (KeyError, TypeError):
                continue
    raise SystemExit("no usable draft pool found in data/")


def build_state(pool, my_team=None):
    """Reconstruct DraftState from the live CLI's exported state."""
    if not os.path.exists(STATE_PATH):
        # no draft running yet -> fresh board
        config = DraftConfig()
        state = DraftState(config, list(pool), {})
        team = my_team if my_team is not None else 0
        return state, team, {'draft_running': False}

    with open(STATE_PATH) as f:
        export = json.load(f)

    config = DraftConfig()
    drafted_ids = set()
    rosters = {}
    picks = []
    name_map = {p.name: p for p in pool}
    for pk in export.get('picks_made', []):
        pl = name_map.get(pk['player'])
        if pl is None:
            continue
        tid = pk['team'] - 1
        rosters.setdefault(tid, []).append(pl)
        picks.append((tid, pl))
        drafted_ids.add(pl.sleeper_id)

    state = DraftState(config, [p for p in pool if p.sleeper_id not in drafted_ids], {})
    from engine import Roster
    state.rosters = {i: Roster(i) for i in range(config.teams)}
    for tid, players in rosters.items():
        state.rosters[tid].players = players
    state.picks_made = picks
    state.current_pick = len(picks)

    team = my_team
    if team is None:
        team = export.get('my_team', 0)
    return state, team, export


def flag_team(argv):
    if '--team' in argv:
        i = argv.index('--team')
        return int(argv[i + 1]) - 1
    return None


def cmd_status(state, team, export):
    c = state.config
    rnd = state.current_pick // c.teams + 1
    print(f"Draft: {state.current_pick}/{c.total_picks} picks (round {rnd})")
    print(f"On the clock: Team {state.current_team() + 1}"
          + ("  <-- YOU" if state.current_team() == team else ""))
    print(f"You: Team {team + 1} with {len(state.rosters[team].players)} players")
    proj = sum(p.projected_pts for p in state.rosters[team].players)
    print(f"Your roster projected (all): {proj:.0f}")
    if export.get('picks_made'):
        print("\nLast 5 picks:")
        for pk in export['picks_made'][-5:]:
            print(f"  R{(pk['pick_number']-1)//c.teams+1}P{(pk['pick_number']-1)%c.teams+1} "
                  f"T{pk['team']}: {pk['player']} ({pk['position']})")


def cmd_recs(state, team, n):
    engine = ValuationEngine(state)
    recs = engine.get_recommendations(team, n)
    rc = engine.roster_construction_score(team)
    print(f"Team {team + 1} recommendations — archetype: {rc['archetype']}")
    if rc['balance_issues']:
        print(f"Issues: {', '.join(rc['balance_issues'])}")
    print(f"{'#':<3}{'Player':<24}{'Pos':<5}{'Team':<5}{'PPR':>7}{'VORP':>8}{'Score':>8}  Note")
    for i, r in enumerate(recs, 1):
        p = r['player']
        print(f"{i:<3}{p.name:<24}{p.position:<5}{p.team:<5}{p.projected_pts:>7.1f}"
              f"{r['vorp']:>8.1f}{r['total_score']:>8.1f}  {r.get('note', '')}")


def cmd_top(state, team, pos, n):
    avail = [p for p in state.available if p.position == pos]
    engine = ValuationEngine(state)
    scored = sorted(((engine.pick_value(p, team), p) for p in avail[:60]),
                    key=lambda x: -x[0]['total_score'])[:n]
    print(f"Top available {pos}:")
    for i, (ev, p) in enumerate(scored, 1):
        extra = f"±{p.rank_std} experts {p.rank_min}-{p.rank_max}" if getattr(p, 'rank_std', 0) else ""
        print(f"{i:>3}. {p.name:<24} {p.team:<4} PPR {p.projected_pts:>6.1f} "
              f"VOR {ev['vorp']:>6.1f} score {ev['total_score']:>6.1f}  {extra}")


def cmd_run(state, team):
    c = state.config
    recent = [p for _, p in state.picks_made[-8:]]
    if len(recent) < 4:
        print("Not enough picks yet for run detection.")
        return
    from collections import Counter
    counts = Counter(p.position for p in recent)
    print("Last 8 picks by position:")
    for pos in ('RB', 'WR', 'TE', 'QB'):
        bar = '#' * counts.get(pos, 0)
        print(f"  {pos}: {counts.get(pos, 0):>2} {bar}")
    hot = max(counts, key=counts.get)
    if counts[hot] >= 4:
        print(f"\nRUN ON {hot}: {counts[hot]}/8 recent picks. "
              f"Best available {hot}: ", end="")
        top = next((p for p in state.available if p.position == hot), None)
        print(top.name if top else "none left in pool")
    else:
        print("\nNo strong positional run detected.")


def cmd_need(state, team, pos):
    roster = state.rosters[team]
    needs = roster.needs(state.config)
    left = [p for p in state.available if p.position == pos]
    drafted = [p for _, p in state.picks_made if p.position == pos]
    c = state.config
    slots = {'QB': c.qb_slots, 'RB': c.rb_slots, 'WR': c.wr_slots, 'TE': c.te_slots}.get(pos, 1)
    print(f"{pos}: {len(drafted)} drafted of ~{c.teams * slots} needed league-wide; "
          f"{len(left)} left in pool ({int(c.teams * slots - len(drafted))} starters still out there)")
    print(f"Your needs: {needs}")
    if left:
        print(f"Best available: {left[0].name} (PPR {left[0].projected_pts:.1f})")
        dropoff = left[0].projected_pts - (left[4].projected_pts if len(left) > 4 else 0)
        print(f"Top-5 depth gap: {dropoff:.1f} pts")


def cmd_compare(state, team, names):
    engine = ValuationEngine(state)
    avail = {p.name.lower(): p for p in state.available}
    picked = []
    for nm in names:
        p = avail.get(nm)
        if not p:
            cand = next((pp for key, pp in avail.items() if nm.lower().split()[-1] in key), None)
            p = cand
        if p:
            picked.append(p)
        else:
            print(f"'{nm}' not available (already drafted or not in pool)")
    if len(picked) < 2:
        return
    rows = []
    for p in picked:
        ev = engine.pick_value(p, team)
        rows.append((p, ev))
    print(f"{'Player':<24}{'PPR':>7}{'VORP':>8}{'Scarcity':>10}{'Urgency':>9}{'Score':>8}")
    for p, ev in sorted(rows, key=lambda x: -x[1]['total_score']):
        print(f"{p.name:<24}{p.projected_pts:>7.1f}{ev['vorp']:>8.1f}"
              f"{ev['scarcity']:>10.2f}{ev.get('urgency', 0):>9.2f}{ev['total_score']:>8.1f}")
    best = max(rows, key=lambda x: x[1]['total_score'])[0]
    print(f"\nEngine prefers: {best.name}")


def main():
    argv = sys.argv[1:]
    team = None
    if '--team' in argv:
        i = argv.index('--team')
        team = int(argv[i + 1]) - 1
        argv = argv[:i] + argv[i + 2:]
    cmd = argv[0] if argv else 'status'
    rest = argv  # rest[0] is the command

    pool, pool_path = load_pool()
    state, team, export = build_state(pool, team)

    if cmd == 'status':
        cmd_status(state, team, export)
    elif cmd == 'recs':
        n = int(rest[1]) if len(rest) > 1 else 6
        cmd_recs(state, team, n)
    elif cmd == 'top':
        pos = rest[1].upper() if len(rest) > 1 else 'RB'
        n = int(rest[2]) if len(rest) > 2 else 8
        cmd_top(state, team, pos, n)
    elif cmd == 'run':
        cmd_run(state, team)
    elif cmd == 'need':
        cmd_need(state, team, rest[1].upper() if len(rest) > 1 else 'RB')
    elif cmd == 'compare':
        cmd_compare(state, team, rest[1:])
    elif cmd == 'json':
        engine = ValuationEngine(state)
        out = {
            'pool': os.path.basename(pool_path),
            'current_pick': state.current_pick,
            'current_team': state.current_team() + 1,
            'my_team': team + 1,
            'available_by_position': {
                pos: len([p for p in state.available if p.position == pos])
                for pos in ('QB', 'RB', 'WR', 'TE')},
            'recommendations': [
                {'player': r['player'].name, 'pos': r['player'].position,
                 'ppr': r['player'].projected_pts, 'vorp': round(r['vorp'], 1),
                 'score': round(r['total_score'], 1), 'note': r.get('note', '')}
                for r in engine.get_recommendations(team, 8)],
        }
        print(json.dumps(out, indent=2))
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
