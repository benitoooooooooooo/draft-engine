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
    def __init__(self, config: DraftConfig, player_pool: List[Player]):
        self.config = config
        self.state = DraftState(config, player_pool, {})
        self.engine = ValuationEngine(self.state)
        self.my_team_id = 0
        
    def display_header(self):
        print("\n" + "="*80)
        print(f"  2O2 DRAFT ENGINE - Round {self.state.current_pick // self.config.teams + 1}, Pick {self.state.current_pick + 1}")
        print(f"  On the clock: Team {self.state.current_team() + 1} {'<<< YOU' if self.state.current_team() == self.my_team_id else ''}")
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
            by_pos[p.position].append(p)
        
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
        print(f"  {'Pick':<6} {'Team':<6} {'Player':<22} {'Pos':<4} {'Team':<5}")
        print(f"  {'-'*50}")
        for i, (team, p) in enumerate(self.state.picks_made[-last_n:], 1):
            print(f"  {len(self.state.picks_made) - last_n + i:<6} {team + 1:<6} {p.name:<22} {p.position:<4} {p.team:<5}")
    
    def search_player(self, query: str) -> Optional[Player]:
        """Find player by name substring"""
        query = query.lower()
        matches = [p for p in self.state.available if query in p.name.lower()]
        if not matches:
            return None
        # Return best match (highest projected)
        matches.sort(key=lambda x: -x.projected_pts)
        return matches[0]
    
    def process_command(self, cmd: str) -> bool:
        """Process a user command. Returns True if draft should continue."""
        cmd = cmd.strip().lower()
        
        if not cmd:
            return True
        
        if cmd.startswith('pick ') or cmd.startswith('p '):
            # Pick a player
            name_query = cmd.split(' ', 1)[1] if ' ' in cmd else ''
            player = self.search_player(name_query)
            if player:
                self.state.make_pick(player)
                self.engine = ValuationEngine(self.state)  # recalc
                print(f"\n  ✓ Pick recorded: {player.name} ({player.position}) to Team {self.state.current_team() + 1}")
            else:
                print(f"\n  ✗ Player not found: {name_query}")
            return True
        
        elif cmd.startswith('opponent ') or cmd.startswith('o '):
            # Opponent pick
            name_query = cmd.split(' ', 1)[1] if ' ' in cmd else ''
            player = self.search_player(name_query)
            if player:
                self.state.make_pick(player)
                self.engine = ValuationEngine(self.state)
                print(f"\n  ✓ Opponent pick: {player.name} ({player.position}) to Team {self.state.current_team() + 1}")
            else:
                print(f"\n  ✗ Player not found: {name_query}")
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
            if player:
                self.state.make_pick(player)
                self.engine = ValuationEngine(self.state)
                print(f"\n  ✓ Pick recorded: {player.name} ({player.position}) to Team {self.state.current_team() + 1}")
            else:
                print(f"\n  Unknown command: {cmd}. Type 'help' for commands.")
            return True
    
    def display_help(self):
        print("""
  COMMANDS:
    pick <name>     - You draft a player (or just type the name)
    opponent <name> - Record opponent's pick
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
        
        # Set your draft position
        while True:
            try:
                pos = input(f"  Enter your draft position (1-{self.config.teams}): ").strip()
                self.my_team_id = int(pos) - 1
                if 0 <= self.my_team_id < self.config.teams:
                    break
            except ValueError:
                pass
            print(f"  Invalid position. Enter 1-{self.config.teams}.")
        
        print(f"\n  You are Team {self.my_team_id + 1}")
        print(f"  Type 'help' for commands\n")
        
        while self.state.current_pick < self.config.total_picks:
            self.display_header()
            
            if self.state.current_team() == self.my_team_id:
                self.display_roster()
                self.display_recommendations()
                self.display_draft_board(6)
                
                cmd = input(f"\n  YOUR PICK >>> ").strip()
                if not self.process_command(cmd):
                    break
            else:
                self.display_draft_board(6)
                cmd = input(f"\n  Opponent {self.state.current_team() + 1} picks (or 'pick <name>' to steal) >>> ").strip()
                if not self.process_command(cmd):
                    break
        
        print("\n  Draft complete!")
        self.display_roster()


def main():
    import os
    os.chdir('/Users/benbrackett/draft-engine')
    
    players = load_draft_pool('data/draft_pool.json')
    config = DraftConfig()
    
    cli = DraftCLI(config, players)
    cli.run()


if __name__ == '__main__':
    main()
