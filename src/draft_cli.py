#!/usr/bin/env python3
"""
Fantasy Football Draft CLI - Live Draft Interface
"""

import sys
import json
from typing import List, Optional
from engine import (
    Player, DraftConfig, DraftState, ValuationEngine,
    load_draft_pool
)


class DraftCLI:
    def __init__(self, config: DraftConfig, player_pool: List[Player], league: Optional[dict] = None):
        self.config = config
        self.state = DraftState(config, player_pool, {})
        self.engine = ValuationEngine(self.state)
        self.my_team_id = 0
        self._notes_mtime = 0
        # league order: {"order": [team names by slot 1..N], "me": "team name"}
        self.league = league or {}
        self.team_names = self.league.get('order', [])
        if self.team_names and self.league.get('me') in self.team_names:
            self.my_team_id = self.team_names.index(self.league['me'])
            self.state.my_team = self.my_team_id

    def team_label(self, team_id: int) -> str:
        name = self.team_names[team_id] if team_id < len(self.team_names) else None
        return f"Team {team_id + 1}" + (f" ({name})" if name else "")

    def display_coach_notes(self):
        """Show Hermes agent notes if coach_notes.txt changed since last check."""
        import os, time
        path = os.path.join(os.path.dirname(__file__), '..', 'coach_notes.txt')
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return
        if mtime <= self._notes_mtime:
            return
        self._notes_mtime = mtime
        with open(path) as f:
            notes = f.read().strip()
        if notes:
            print("\n  " + "="*62)
            print("  📝 COACH NOTES (Hermes):")
            for line in notes.splitlines():
                print(f"    {line}")
            print("  " + "="*62)
        
    def display_header(self):
        print("\n" + "="*80)
        print(f"  2O2 DRAFT ENGINE - Round {self.state.current_pick // self.config.teams + 1}, Pick {self.state.current_pick + 1}")
        print(f"  On the clock: {self.team_label(self.state.current_team())} {'<<< YOU' if self.state.current_team() == self.my_team_id else ''}")
        print("="*80)
    
    def display_roster(self, team_id: Optional[int] = None):
        if team_id is None:
            team_id = self.my_team_id
        roster = self.state.rosters[team_id]
        
        # Get roster construction analysis
        rc = self.engine.roster_construction_score(team_id)
        
        print(f"\n  YOUR ROSTER (Team {team_id + 1}) - Archetype: {rc['archetype']}")
        print(f"  {'-'*60}")
        
        pos_order = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'BENCH']
        by_pos = {pos: [] for pos in pos_order}
        
        for p in roster.players:
            by_pos.setdefault(p.position, []).append(p)
        
        # Starters
        starters_shown = 0
        for pos in ['QB', 'RB', 'WR', 'TE']:
            slots = getattr(self.config, f'{pos.lower()}_slots')
            for i in range(slots):
                if i < len(by_pos[pos]):
                    p = by_pos[pos][i]
                    print(f"  [{pos}] {p.name:20s} {p.team:4s}  Proj: {p.projected_pts:.1f}")
                else:
                    print(f"  [{pos}] {'(empty)':20s}")
                starters_shown += 1
        
        # Flex
        flex_filled = 0
        flex_candidates = []
        for pos in ['RB', 'WR', 'TE']:
            slots = getattr(self.config, f'{pos.lower()}_slots')
            extra = by_pos[pos][slots:] if len(by_pos[pos]) > slots else []
            flex_candidates.extend([(p, pos) for p in extra])
        
        flex_candidates.sort(key=lambda x: -x[0].projected_pts)
        if flex_candidates:
            p, pos = flex_candidates[0]
            print(f"  [FLEX] {p.name:18s} {p.team:4s}  Proj: {p.projected_pts:.1f} ({pos})")
        else:
            print(f"  [FLEX] {'(empty)':18s}")
        
        # Bench
        bench_count = len(roster.players) - starters_shown - (1 if flex_candidates else 0)
        print(f"\n  Bench ({bench_count}/{self.config.bench_slots}):")
        bench_players = []
        for pos in ['RB', 'WR', 'TE', 'QB']:
            slots = getattr(self.config, f'{pos.lower()}_slots')
            if pos == 'RB':
                slots += 1  # account for flex
            extra = by_pos[pos][slots:] if len(by_pos[pos]) > slots else []
            bench_players.extend(extra)
        
        for p in bench_players[:self.config.bench_slots]:
            print(f"    {p.position:3s} {p.name:20s} {p.team:4s}  Proj: {p.projected_pts:.1f}")
        
        # Roster construction analysis
        print(f"\n  Roster Quality:")
        print(f"    RB: {rc['rb_quality']:.1f} pts/starter  |  WR: {rc['wr_quality']:.1f} pts/starter")
        print(f"    TE: {rc['te_quality']:.1f} pts          |  QB: {rc['qb_quality']:.1f} pts")
        if rc['balance_issues']:
            print(f"\n  ⚠️  Issues: {', '.join(rc['balance_issues'])}")
        if rc['recommended_next'] != 'BPA':
            print(f"  → Recommended next: {rc['recommended_next']}")
    
    def display_recommendations(self):
        if self.state.current_team() != self.my_team_id:
            return
            
        print(f"\n  >>> YOUR RECOMMENDATIONS <<<")
        print(f"  {'Rank':<6} {'Player':<22} {'Pos':<4} {'Team':<5} {'VORP':<7} {'Urgency':<8} {'Score':<7} {'Note'}")
        print(f"  {'-'*100}")
        
        recs = self.engine.get_recommendations(self.my_team_id, 10)
        
        for i, r in enumerate(recs, 1):
            p = r['player']
            note = ""
            if r.get('opponent_pressure'):
                note = "OPPONENTS NEED THIS"
            elif r['dropoff_risk'] > 0.7:
                note = "WON'T MAKE IT BACK"
            elif r['scarcity'] > 0.6:
                note = "POSITION CLIFF"
            elif r['need_bonus'] > 15:
                note = "FILL NEED"
            
            print(f"  {i:<6} {p.name:<22} {p.position:<4} {p.team:<5} {r['vorp']:<7.1f} {r['urgency']:<8.2f} {r['total_score']:<7.1f} {note}")
        
        # Positional options board: best available at each value position
        wide = self.engine.get_recommendations(self.my_team_id, 60)
        needs = self.state.rosters[self.my_team_id].needs(self.config)
        best_score = wide[0]['total_score'] if wide else 0
        by_pos = {}
        for r in wide:
            pos = r['player'].position
            if pos not in by_pos:
                by_pos[pos] = []
            if len(by_pos[pos]) < 2:
                by_pos[pos].append(r)
        print(f"\n  ▸ BEST AT EACH POSITION (cost = engine score vs overall #1)")
        print(f"  {'Pos':<5}{'':<2}{'Player':<22}{'Team':<5}{'PPR':>7}{'VORP':>8}{'Score':>8}{'Cost':>7}  Note")
        for pos in ('RB', 'WR', 'TE', 'QB'):
            need_n = needs.get(pos, 0)
            tag = "  NEED" if need_n else ""
            rows = by_pos.get(pos, [])
            if not rows:
                print(f"  {pos:<5}  {'(none available)':<22}")
                continue
            for j, r in enumerate(rows):
                p = r['player']
                cost = r['total_score'] - best_score
                if j == 0 and r['dropoff_risk'] > 0.7 and need_n:
                    dn = "⛔ won't last to next pick"
                elif j == 1 and rows and cost > -25:
                    dn = "≈ same value as #1 pick overall" if abs(cost) < 25 else ""
                else:
                    dn = ""
                label = f"{pos:<5}" if j == 0 else "     "
                print(f"  {label}{'1.' if j==0 else '2.'} {p.name:<22}{p.team:<5}{p.projected_pts:>7.0f}{r['vorp']:>8.1f}"
                      f"{r['total_score']:>8.1f}{cost:>+7.0f}  {dn}{tag if j==0 else ''}")
        
        # Show opponent pressure summary
        opp_needs = self.engine._aggregate_opponent_needs(self.my_team_id)
        if opp_needs:
            pressure = [f"{k}:{v}" for k, v in opp_needs.items() if v >= 3]
            if pressure:
                print(f"\n  👀 Opponent needs: {', '.join(pressure)} teams need these positions")
        
        # Show positional run alert
        self._check_positional_runs()
    
    def _check_positional_runs(self):
        """Alert if a position is being drafted heavily"""
        recent_picks = [p for _, p in self.state.picks_made[-12:]]
        if not recent_picks:
            return
            
        rb_count = sum(1 for p in recent_picks if p.position == 'RB')
        wr_count = sum(1 for p in recent_picks if p.position == 'WR')
        te_count = sum(1 for p in recent_picks if p.position == 'TE')
        
        if rb_count >= 5:
            print(f"\n  ⚠️  RB RUN DETECTED: {rb_count} RBs in last {len(recent_picks)} picks!")
            remaining_rb_starters = self._count_remaining_starters('RB')
            print(f"      Estimated RB starters remaining: {remaining_rb_starters}")
        
        if wr_count >= 5:
            print(f"\n  ⚠️  WR RUN DETECTED: {wr_count} WRs in last {len(recent_picks)} picks!")
        
        if te_count >= 3:
            print(f"\n  ⚠️  TE RUN DETECTED: {te_count} TEs in last {len(recent_picks)} picks!")
    
    def _count_remaining_starters(self, position: str) -> int:
        """Rough estimate of how many starter-quality players remain"""
        by_pos = [p for p in self.state.available if p.position == position]
        by_pos.sort(key=lambda x: -x.projected_pts)
        
        # Starter quality = above replacement
        rep = self.engine._replacement_values.get(position, 0)
        above_rep = [p for p in by_pos if p.projected_pts > rep]
        return len(above_rep)
    
    def display_available_by_position(self, position: str, limit: int = 15):
        """Show top available at a position"""
        players = [p for p in self.state.available if p.position == position]
        players.sort(key=lambda x: -x.projected_pts)
        
        print(f"\n  TOP AVAILABLE {position}s:")
        print(f"  {'Rank':<6} {'Player':<22} {'Team':<5} {'Proj':<7} {'VORP':<7}")
        print(f"  {'-'*50}")
        for i, p in enumerate(players[:limit], 1):
            vorp = self.engine.vorp(p)
            print(f"  {i:<6} {p.name:<22} {p.team:<5} {p.projected_pts:<7.1f} {vorp:<7.1f}")
    
    def display_draft_board(self, last_n: int = 12):
        """Show recent picks"""
        if not self.state.picks_made:
            return
        
        print(f"\n  LAST {min(last_n, len(self.state.picks_made))} PICKS:")
        print(f"  {'Pick':<6} {'Team':<10} {'Player':<22} {'Pos':<4} {'NFL Team':<5}")
        print(f"  {'-'*50}")
        for i, (team, p) in enumerate(self.state.picks_made[-last_n:], 1):
            label = self.team_label(team).replace('Team ', 'T')
            print(f"  {len(self.state.picks_made) - last_n + i:<6} {label:<10} {p.name:<22} {p.position:<4} {p.team:<5}")
    
    def search_player(self, query: str) -> Optional[Player]:
        """Find player by name — substring, initial, or fuzzy (typo-tolerant).
        Ambiguous matches across DIFFERENT last names are rejected with candidates
        instead of silently picking one."""
        import re as _re
        import difflib
        def norm(s):
            s = s.lower().replace("'", '').replace('\u2019', '')
            return _re.sub(r'[^a-z0-9 ]', ' ', s).split()
        q_tokens = norm(query)
        if not q_tokens:
            return None
        qn = ' '.join(q_tokens)
        cands = []
        for p in self.state.available:
            pn = ' '.join(norm(p.name))
            pt = norm(p.name)
            exact = pn == qn
            substr = qn in pn or (len(q_tokens) == 1 and any(t.startswith(q_tokens[0]) for t in pt))
            # initials: "j gibbs", "gibbs j", "jb" won't match but "j gibbs" will
            init = False
            if len(q_tokens) == 2 and len(pt) >= 2:
                a, b = q_tokens
                init = ((pt[-1].startswith(a) and pt[0][0] == b[0]) or
                        (pt[-1].startswith(b) and pt[0][0] == a[0]))
            if exact:
                return p
            if substr or init:
                cands.append((0 if exact else 1, p))
        # fuzzy fallback for typos (only when nothing matched) — per-token and full-name
        if not cands and len(qn) > 3:
            names = {' '.join(norm(p.name)): p for p in self.state.available}
            seen = {}
            for fname, p in names.items():
                if difflib.get_close_matches(qn, [fname], cutoff=0.75):
                    seen[p.sleeper_id] = p
                    continue
                for t in norm(p.name):
                    if len(t) > 3 and difflib.get_close_matches(qn, [t], cutoff=0.8):
                        seen[p.sleeper_id] = p
                        break
            cands = [(2, p) for p in list(seen.values())[:3]]
        if not cands:
            return None
        # ambiguity: resolve by engine value (the one the engine ranks highest)
        if len(cands) > 1:
            try:
                cands.sort(key=lambda x: (-x[0], -self.engine.pick_value(x[1], self.my_team_id)['total_score']))
            except Exception:
                cands.sort(key=lambda x: (x[0], -x[1].projected_pts))
            if len({p.name for _, p in cands}) > 1:
                names = ', '.join(p.name for _, p in cands[:3])
                print(f"  ⚠ '{query}' matched multiple ({names}) — using {cands[0][1].name}")
        else:
            cands.sort(key=lambda x: (x[0], -x[1].projected_pts))
        return cands[0][1]
    
    def process_command(self, cmd: str) -> bool:
        """Process a user command. Returns True if draft should continue."""
        cmd = cmd.strip().lower()
        
        if not cmd:
            return True
        
        if cmd.startswith('pick ') or cmd.startswith('p '):
            # Pick a player
            name_query = cmd.split(' ', 1)[1] if ' ' in cmd else ''
            player = self.search_player(name_query)
            clocked = self.team_label(self.state.current_team())  # capture BEFORE make_pick advances
            if player:
                self.state.make_pick(player)
                self.engine = ValuationEngine(self.state)  # recalc
                print(f"\n  ✓ Pick recorded: {player.name} ({player.position}) to {clocked}")
            elif name_query:
                from engine import Player as P
                ph = P(rank=9999, name=name_query.title(), position='?', team='?',
                       projected_pts=0.0, tier=9, sleeper_id=f"off_{self.state.current_pick}")
                self.state.make_pick(ph)
                self.engine = ValuationEngine(self.state)
                print(f"\n  ✓ Recorded off-pool pick: {ph.name} ({clocked})")
            else:
                print(f"\n  ✗ Player not found: {name_query}")
            return True
        
        elif cmd.startswith('opponent ') or cmd.startswith('o '):
            # Opponent pick
            name_query = cmd.split(' ', 1)[1] if ' ' in cmd else ''
            player = self.search_player(name_query)
            clocked = self.team_label(self.state.current_team())  # capture BEFORE advance
            if player:
                self.state.make_pick(player)
                self.engine = ValuationEngine(self.state)
                print(f"\n  ✓ Opponent pick: {player.name} ({player.position}) to {clocked}")
            elif name_query:
                # Off-pool pick (Kicker/DST/etc) — placeholder keeps the snake advancing
                from engine import Player as P
                ph = P(rank=9999, name=name_query.title(), position='?', team='?',
                       projected_pts=0.0, tier=9, sleeper_id=f"off_{self.state.current_pick}")
                self.state.make_pick(ph)
                self.engine = ValuationEngine(self.state)
                print(f"\n  ✓ Recorded off-pool pick: {ph.name} to {clocked} (K/DST?)")
            else:
                print(f"\n  ✗ Usage: o <name>")
            return True
        
        elif cmd in ('k', 'kickers', 'dst', 'defense'):
            print(f"\n  K/DST aren't ranked in the pool — just record them directly:")
            print(f"    o <name>   (opponent's K/DST)   or   pick <name>   (yours)")
            print(f"  Kicker ECR ref (scraped today): Fairbairn/Dicker/Little/Myers top the board.")
            return True
        
        elif cmd.startswith('clock '):
            # Resync the snake after a missed/extra pick feed:
            #   clock <team name or number>  -> fast-forward to that team's next slot
            # Skipped slots get '???' placeholders (names lost, pool stays correct).
            target = cmd.split(' ', 1)[1].strip().lower()
            tid = None
            if target.isdigit():
                tid = int(target) - 1
            elif self.team_names:
                for i, nm in enumerate(self.team_names):
                    if target == nm.lower() or target in nm.lower():
                        tid = i
                        break
            if tid is None or not (0 <= tid < self.config.teams):
                print("\n  Unknown team. Usage: clock <team name|number>")
                return True
            cp = self.state.current_pick
            cand = None
            for c in range(cp, self.config.total_picks):
                saved = self.state.current_pick
                self.state.current_pick = c
                who = self.state.current_team()
                self.state.current_pick = saved
                if who == tid:
                    cand = c
                    break
            if cand is None:
                print("\n  That team has no remaining picks.")
                return True
            from engine import Player as P
            advanced = 0
            for c in range(cp, cand):
                saved = self.state.current_pick
                self.state.current_pick = c
                owner = self.state.current_team()
                self.state.current_pick = saved
                ph = P(rank=9999, name='???', position='?', team='?',
                       projected_pts=0.0, tier=9, sleeper_id=f"skipped_{c}")
                self.state.rosters[owner].players.append(ph)
                self.state.picks_made.append((owner, ph))
                self.state.current_pick = c + 1
                advanced += 1
            self.state._export_state()
            self.engine = ValuationEngine(self.state)
            skip_msg = f" ({advanced} slot{'s' if advanced != 1 else ''} filled with ???)" if advanced else ""
            print(f"\n  ⏱ Clock resynced: pick {self.state.current_pick + 1} = {self.team_label(tid)}{skip_msg}")
            return True

        elif cmd == 'undo':
            # Remove the last recorded pick (typo rescue)
            result = self.state.undo_last_pick()
            self.engine = ValuationEngine(self.state)
            if result:
                team, player = result
                print(f"\n  ↩ Undid: {player.name} ({player.position}) from {self.team_label(team)} — pick {self.state.current_pick + 1} is up again")
            else:
                print("\n  Nothing to undo.")
            return True
        
        elif cmd == 'pass':
            # Record an off-pool pick (your K/DST round) for the team on the clock
            clocked = self.team_label(self.state.current_team())
            name_query = 'Kicker' if self.state.current_pick % 2 else 'DST'
            from engine import Player as P
            ph = P(rank=9999, name=name_query, position='?', team='?',
                   projected_pts=0.0, tier=9, sleeper_id=f"off_{self.state.current_pick}")
            self.state.make_pick(ph)
            self.engine = ValuationEngine(self.state)
            print(f"\n  ✓ Pass recorded for {clocked} (clock advanced)")
            return True
        
        elif cmd == 'rb' or cmd == 'rbs':
            self.display_available_by_position('RB')
            return True
        
        elif cmd == 'wr' or cmd == 'wrs':
            self.display_available_by_position('WR')
            return True
        
        elif cmd == 'te' or cmd == 'tes':
            self.display_available_by_position('TE')
            return True
        
        elif cmd == 'qb' or cmd == 'qbs':
            self.display_available_by_position('QB')
            return True
        
        elif cmd == 'recs' or cmd == 'r':
            self.display_recommendations()
            return True
        
        elif cmd == 'roster' or cmd == 'r':
            self.display_roster()
            return True
        
        elif cmd == 'board' or cmd == 'b':
            self.display_draft_board()
            return True
        
        elif cmd == 'all':
            self.display_available_by_position('RB', 10)
            self.display_available_by_position('WR', 10)
            self.display_available_by_position('TE', 8)
            self.display_available_by_position('QB', 8)
            return True
        
        elif cmd == 'help' or cmd == 'h':
            self.display_help()
            return True
        
        elif cmd == 'quit' or cmd == 'q':
            return False
        
        else:
            # Try to interpret as a pick
            player = self.search_player(cmd)
            clocked = self.team_label(self.state.current_team())
            if player:
                self.state.make_pick(player)
                self.engine = ValuationEngine(self.state)
                print(f"\n  ✓ Pick recorded: {player.name} ({player.position}) to {clocked}")
            elif len(cmd) > 2 and ' ' not in cmd[:2] and cmd not in ('h', 'b'):
                # Not in skill pool (late-round RB/WR, K, DST) — record placeholder
                from engine import Player as P
                ph = P(rank=9999, name=cmd.title(), position='?', team='?',
                       projected_pts=0.0, tier=9, sleeper_id=f"off_{self.state.current_pick}")
                self.state.make_pick(ph)
                self.engine = ValuationEngine(self.state)
                print(f"\n  ✓ {ph.name} not in skill pool — recorded as off-pool pick to {clocked}")
                print(f"    (wrong? type 'undo' then the correct name)")
            else:
                print(f"\n  Unknown command: {cmd}. Type 'help' for commands.")
            return True
    
    def display_help(self):
        print("""
  COMMANDS:
    pick <name>     - You draft a player (or just type the name; unknown
                      names record as off-pool picks so nothing stalls)
    opponent <name> - Record opponent's pick
    undo            - Remove the last pick (typo fix — that team picks again)
    clock <team>    - Resync after a missed feed: fast-forward to that team's
                      next slot (skipped slots become ??? placeholders)
    pass            - Record K/DST pick for whoever is on the clock
    k / dst         - Kicker/defense board reference
    rb / wr / te / qb - Show top available at that position
    recs            - Show your recommendations
    roster          - Show your roster
    board           - Show recent picks
    all             - Show top available at all positions
    help            - This help
    quit            - Exit
        """)
    
    def run(self):
        print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║           2O2 FANTASY FOOTBALL DRAFT ENGINE                   ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
        """)
        
        # Set your draft position (skipped if league.json defines "me")
        if not self.team_names:
            while True:
                try:
                    pos = input(f"  Enter your draft position (1-{self.config.teams}): ").strip()
                    self.my_team_id = int(pos) - 1
                    if 0 <= self.my_team_id < self.config.teams:
                        self.state.my_team = self.my_team_id
                        break
                except ValueError:
                    pass
                print(f"  Invalid position. Enter 1-{self.config.teams}.")
        
        if self.team_names:
            print("  LEAGUE SNAKE ORDER (slot 1 picks 1/20, slot 2 picks 2/19, ...):")
            for i, name in enumerate(self.team_names):
                mark = "  <<< YOU" if i == self.my_team_id else ""
                print(f"    {i + 1:>2}. {name}{mark}")
            print()
        print(f"\n  You are {self.team_label(self.my_team_id)}")
        print(f"  Type 'help' for commands\n")
        
        while self.state.current_pick < self.config.total_picks:
            self.display_header()
            
            if self.state.current_team() == self.my_team_id:
                self.display_roster()
                self.display_recommendations()
                self.display_draft_board(6)
                self.display_coach_notes()
                
                cmd = input(f"\n  YOUR PICK >>> ").strip()
                if not self.process_command(cmd):
                    break
            else:
                self.display_draft_board(6)
                self.display_coach_notes()
                cmd = input(f"\n  {self.team_label(self.state.current_team())} picks (or 'pick <name>' to steal) >>> ").strip()
                if not self.process_command(cmd):
                    break
        
        print("\n  Draft complete!")
        self.display_roster()


def main():
    import os
    os.chdir('/Users/benbrackett/draft-engine')
    
    players = load_draft_pool('data/draft_pool.json')
    config = DraftConfig()
    
    league = {}
    if os.path.exists('league.json'):
        league = json.load(open('league.json'))
        if league.get('teams'):
            config.teams = league['teams']
        for key in ('qb_slots', 'rb_slots', 'wr_slots', 'te_slots',
                    'flex_slots', 'bench_slots', 'k_slots', 'dst_slots'):
            if key in league:
                setattr(config, key, league[key])
        # keep roster size consistent unless explicitly set
        if 'roster_spots' in league:
            config.roster_spots = league['roster_spots']
        else:
            config.roster_spots = (config.qb_slots + config.rb_slots + config.wr_slots +
                                   config.te_slots + config.flex_slots + config.k_slots +
                                   config.dst_slots + config.bench_slots)
    
    cli = DraftCLI(config, players, league)
    cli.run()


if __name__ == '__main__':
    main()
