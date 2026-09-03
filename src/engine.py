#!/usr/bin/env python3
"""
Fantasy Football Draft Engine - Core Valuation & Draft Logic
"""

import json
import math
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

@dataclass
class Player:
    rank: int
    name: str
    position: str
    team: str
    projected_pts: float
    tier: int
    sleeper_id: str

@dataclass
class DraftConfig:
    teams: int = 10
    roster_spots: int = 16
    qb_slots: int = 1
    rb_slots: int = 2
    wr_slots: int = 2
    te_slots: int = 1
    flex_slots: int = 1
    k_slots: int = 1
    dst_slots: int = 1
    bench_slots: int = 7
    scoring: str = "PPR"
    
    @property
    def total_picks(self) -> int:
        return self.teams * self.roster_spots
    
    @property
    def starters(self) -> int:
        return self.qb_slots + self.rb_slots + self.wr_slots + self.te_slots + self.flex_slots

@dataclass
class Roster:
    team_id: int
    players: List[Player] = field(default_factory=list)
    
    def count_position(self, pos: str) -> int:
        return sum(1 for p in self.players if p.position == pos)
    
    def needs(self, config: DraftConfig) -> Dict[str, int]:
        """Return how many more of each position needed"""
        needs = {}
        needs['QB'] = max(0, config.qb_slots - self.count_position('QB'))
        needs['RB'] = max(0, config.rb_slots - self.count_position('RB'))
        needs['WR'] = max(0, config.wr_slots - self.count_position('WR'))
        needs['TE'] = max(0, config.te_slots - self.count_position('TE'))
        # Flex can be RB/WR/TE
        flex_filled = min(
            self.count_position('RB') - config.rb_slots,
            self.count_position('WR') - config.wr_slots,
            self.count_position('TE') - config.te_slots,
            config.flex_slots
        )
        needs['FLEX'] = max(0, config.flex_slots - flex_filled)
        return needs
    
    def is_full(self, config: DraftConfig) -> bool:
        return len(self.players) >= config.roster_spots

@dataclass  
class DraftState:
    config: DraftConfig
    available: List[Player]
    rosters: Dict[int, Roster]
    picks_made: List[Tuple[int, Player]] = field(default_factory=list)
    current_pick: int = 0
    
    def __post_init__(self):
        if not self.rosters:
            self.rosters = {i: Roster(i) for i in range(self.config.teams)}
    
    def current_team(self) -> int:
        """Which team is on the clock"""
        round_num = self.current_pick // self.config.teams
        pick_in_round = self.current_pick % self.config.teams
        if round_num % 2 == 0:
            return pick_in_round
        else:
            return self.config.teams - 1 - pick_in_round
    
    def picks_until_turn(self, team_id: int) -> int:
        """How many picks until this team is on the clock again"""
        current = self.current_team()
        if current == team_id:
            return 0
        
        round_num = self.current_pick // self.config.teams
        pick_in_round = self.current_pick % self.config.teams
        
        if round_num % 2 == 0:  # forward
            if pick_in_round < team_id:
                return team_id - pick_in_round
            else:
                # wait until next round (snake back)
                return (self.config.teams - pick_in_round) + (self.config.teams - 1 - team_id)
        else:  # reverse
            reverse_pick = self.config.teams - 1 - pick_in_round
            if reverse_pick > team_id:
                return reverse_pick - team_id
            else:
                return (reverse_pick + 1) + team_id
    
    def make_pick(self, player: Player):
        """Record a pick"""
        team = self.current_team()
        self.rosters[team].players.append(player)
        self.picks_made.append((team, player))
        self.available = [p for p in self.available if p.sleeper_id != player.sleeper_id]
        self.current_pick += 1


class ValuationEngine:
    """Calculates VORP, positional scarcity, and pick recommendations"""
    
    def __init__(self, state: DraftState):
        self.state = state
        self._replacement_values = {}
        self._compute_replacement_levels()
    
    def _compute_replacement_levels(self):
        """Find replacement level (best available at each position that would be a bench player)"""
        by_pos = defaultdict(list)
        for p in self.state.available:
            by_pos[p.position].append(p)
        
        # Sort by projected points
        for pos in by_pos:
            by_pos[pos].sort(key=lambda x: -x.projected_pts)
        
        # Replacement level = best player who would be on bench
        # For each position, estimate how many starters are needed
        config = self.state.config
        starters_per_pos = {
            'QB': config.qb_slots * config.teams,
            'RB': (config.rb_slots + config.flex_slots) * config.teams,  # RBs fill flex too
            'WR': (config.wr_slots + config.flex_slots) * config.teams,
            'TE': (config.te_slots + 0.3 * config.flex_slots) * config.teams,  # TEs rarely flex
        }
        
        for pos, players in by_pos.items():
            idx = int(starters_per_pos.get(pos, 12))
            if len(players) > idx:
                self._replacement_values[pos] = players[idx].projected_pts
            elif players:
                self._replacement_values[pos] = players[-1].projected_pts
            else:
                self._replacement_values[pos] = 0
    
    def vorp(self, player: Player) -> float:
        """Value Over Replacement Player"""
        rep = self._replacement_values.get(player.position, 0)
        return player.projected_pts - rep
    
    def positional_scarcity(self, position: str) -> float:
        """How scarce is this position? 0 = deep, 1 = dry"""
        by_pos = [p for p in self.state.available if p.position == position]
        if not by_pos:
            return 1.0
        
        by_pos.sort(key=lambda x: -x.projected_pts)
        
        config = self.state.config
        if position == 'RB':
            starters_needed = (config.rb_slots + config.flex_slots) * config.teams
        elif position == 'WR':
            starters_needed = (config.wr_slots + config.flex_slots) * config.teams
        elif position == 'TE':
            starters_needed = config.te_slots * config.teams
        else:
            starters_needed = config.qb_slots * config.teams
        
        # Tier-based scarcity: how many STARTER QUALITY players remain vs needed
        # Starter quality = top N where N is starters needed across all teams
        total_starters = starters_needed
        quality_players = by_pos[:total_starters] if len(by_pos) >= total_starters else by_pos
        
        # Drop-off: difference between best available and replacement
        rep = self._replacement_values.get(position, 0)
        best = by_pos[0].projected_pts if by_pos else 0
        dropoff_magnitude = (best - rep) / max(best, 1)
        
        # Scarcity combines: how thin is quality depth + how big is the cliff
        above_rep = sum(1 for p in by_pos if p.projected_pts > rep)
        depth_ratio = above_rep / max(total_starters, 1)
        
        scarcity = (1.0 - min(1.0, depth_ratio)) * 0.6 + dropoff_magnitude * 0.4
        return min(1.0, scarcity)
    
    def dropoff_risk(self, player: Player, picks_until_next: int) -> float:
        """Probability this player won't make it back to your next pick"""
        # Simple model: estimate based on ADP gap
        by_pos = [p for p in self.state.available if p.position == player.position]
        by_pos.sort(key=lambda x: -x.projected_pts)
        
        rank_in_pos = next((i for i, p in enumerate(by_pos) if p.sleeper_id == player.sleeper_id), len(by_pos))
        
        # If fewer players at this position than picks until next turn, risk is high
        players_at_pos_after = len(by_pos) - rank_in_pos - 1
        if players_at_pos_after <= picks_until_next // 2:  # heuristic
            return 0.9
        elif players_at_pos_after <= picks_until_next:
            return 0.7
        elif players_at_pos_after <= picks_until_next * 2:
            return 0.4
        return 0.1
    
    def pick_value(self, player: Player, team_id: int) -> Dict:
        """Full valuation for a potential pick"""
        vor = self.vorp(player)
        scarcity = self.positional_scarcity(player.position)
        picks_until = self.state.picks_until_turn(team_id)
        dropoff = self.dropoff_risk(player, picks_until) if picks_until > 0 else 0
        
        # Urgency score: combines scarcity + dropoff risk
        urgency = (scarcity * 0.6) + (dropoff * 0.4)
        
        # Needs adjustment
        needs = self.state.rosters[team_id].needs(self.state.config)
        need_bonus = 0
        if player.position == 'RB' and needs.get('RB', 0) > 0:
            need_bonus = 15
        elif player.position == 'WR' and needs.get('WR', 0) > 0:
            need_bonus = 12
        elif player.position == 'TE' and needs.get('TE', 0) > 0:
            need_bonus = 20  # TE scarcity makes needs more urgent
        elif player.position == 'QB' and needs.get('QB', 0) > 0:
            need_bonus = 8
        
        # Total score
        total_score = vor + (urgency * 30) + need_bonus
        
        return {
            'player': player,
            'vorp': round(vor, 1),
            'scarcity': round(scarcity, 2),
            'dropoff_risk': round(dropoff, 2),
            'urgency': round(urgency, 2),
            'need_bonus': need_bonus,
            'total_score': round(total_score, 1),
            'picks_until_next': picks_until
        }
    
    def get_recommendations(self, team_id: int, top_n: int = 8) -> List[Dict]:
        """Get top recommendations for a team with opponent-aware urgency"""
        vals = [self.pick_value(p, team_id) for p in self.state.available]
        
        # Adjust for opponent needs - boost players that opponents will likely take
        opp_needs = self._aggregate_opponent_needs(team_id)
        for v in vals:
            p = v['player']
            if opp_needs.get(p.position, 0) > self.state.config.teams // 3:
                # Many opponents need this position - increase urgency
                v['total_score'] += 8
                v['opponent_pressure'] = True
        
        vals.sort(key=lambda x: -x['total_score'])
        return vals[:top_n]
    
    def _aggregate_opponent_needs(self, my_team_id: int) -> Dict[str, int]:
        """Count how many opponents still need each position"""
        needs = defaultdict(int)
        for tid, roster in self.state.rosters.items():
            if tid == my_team_id:
                continue
            if roster.is_full(self.state.config):
                continue
            roster_needs = roster.needs(self.state.config)
            for pos, count in roster_needs.items():
                if count > 0:
                    needs[pos] += 1
        return dict(needs)
    
    def opponent_threat_level(self, player: Player, my_team_id: int) -> float:
        """How likely is an opponent to take this player before my next pick?"""
        picks_until = self.state.picks_until_turn(my_team_id)
        if picks_until <= 1:
            return 0.0  # I'm picking now
        
        # Count opponents between now and my next pick who need this position
        threatening_opps = 0
        for i in range(1, picks_until):
            pick_num = self.state.current_pick + i
            round_num = pick_num // self.state.config.teams
            pick_in_round = pick_num % self.state.config.teams
            if round_num % 2 == 0:
                opp_id = pick_in_round
            else:
                opp_id = self.state.config.teams - 1 - pick_in_round
            
            if opp_id == my_team_id:
                continue
            
            opp_needs = self.state.rosters[opp_id].needs(self.state.config)
            if opp_needs.get(player.position, 0) > 0:
                threatening_opps += 1
        
        return threatening_opps / max(picks_until - 1, 1)
    
    def roster_construction_score(self, team_id: int) -> Dict:
        """Evaluate how well-constructed a roster is"""
        roster = self.state.rosters[team_id]
        config = self.state.config
        
        pos_counts = defaultdict(int)
        for p in roster.players:
            pos_counts[p.position] += 1
        
        # Calculate projected starters
        rb_starters = min(pos_counts['RB'], config.rb_slots)
        wr_starters = min(pos_counts['WR'], config.wr_slots)
        te_starters = min(pos_counts['TE'], config.te_slots)
        qb_starters = min(pos_counts['QB'], config.qb_slots)
        
        # Flex goes to best remaining
        flex_from_rb = max(0, pos_counts['RB'] - config.rb_slots)
        flex_from_wr = max(0, pos_counts['WR'] - config.wr_slots)
        flex_from_te = max(0, pos_counts['TE'] - config.te_slots)
        
        # Grade roster balance
        balance_issues = []
        picks_so_far = len(roster.players)
        
        # Early round expectations
        if picks_so_far >= 3 and pos_counts['RB'] < 1:
            balance_issues.append("No RB through 3 picks")
        if picks_so_far >= 5 and pos_counts['WR'] < 2:
            balance_issues.append("Light on WRs")
        if picks_so_far >= 7 and pos_counts['RB'] < 2:
            balance_issues.append("RB deficient for flex")
        if picks_so_far >= 4 and pos_counts['TE'] == 0:
            # Check if elite TEs are gone
            te_gone = sum(1 for _, p in self.state.picks_made if p.position == 'TE')
            if te_gone >= 3:
                balance_issues.append("Missed TE tier, consider punting")
        
        # Position strength scores
        rb_quality = 0
        if pos_counts['RB'] > 0:
            rb_pts = sorted([p.projected_pts for p in roster.players if p.position == 'RB'], reverse=True)
            rb_quality = sum(rb_pts[:config.rb_slots + config.flex_slots]) / max(len(rb_pts[:config.rb_slots + config.flex_slots]), 1)
        
        wr_quality = 0
        if pos_counts['WR'] > 0:
            wr_pts = sorted([p.projected_pts for p in roster.players if p.position == 'WR'], reverse=True)
            wr_quality = sum(wr_pts[:config.wr_slots + config.flex_slots]) / max(len(wr_pts[:config.wr_slots + config.flex_slots]), 1)
        
        te_quality = 0
        if pos_counts['TE'] > 0:
            te_pts = [p.projected_pts for p in roster.players if p.position == 'TE']
            te_quality = max(te_pts) if te_pts else 0
        
        qb_quality = 0
        if pos_counts['QB'] > 0:
            qb_pts = [p.projected_pts for p in roster.players if p.position == 'QB']
            qb_quality = max(qb_pts) if qb_pts else 0
        
        # Draft path archetype
        archetype = "Balanced"
        if pos_counts['RB'] >= 3 and pos_counts['WR'] <= 2 and picks_so_far <= 6:
            archetype = "RB Heavy"
        elif pos_counts['WR'] >= 4 and pos_counts['RB'] <= 1 and picks_so_far <= 6:
            archetype = "Zero RB"
        elif pos_counts['TE'] >= 1 and te_quality > 240:
            archetype = "Elite TE Anchor"
        elif pos_counts['QB'] >= 1 and qb_quality > 340:
            archetype = "Early QB"
        
        # Recommended next position
        needs = roster.needs(config)
        rec_pos = None
        if needs.get('RB', 0) >= 2 and picks_so_far < 8:
            rec_pos = 'RB'
        elif needs.get('WR', 0) >= 2 and picks_so_far < 8:
            rec_pos = 'WR'
        elif needs.get('TE', 0) > 0 and picks_so_far < 6:
            rec_pos = 'TE'
        elif needs.get('QB', 0) > 0 and picks_so_far > 8:
            rec_pos = 'QB'
        elif needs.get('RB', 0) > 0:
            rec_pos = 'RB'
        else:
            rec_pos = 'BPA'
        
        return {
            'rb_count': pos_counts['RB'],
            'wr_count': pos_counts['WR'],
            'te_count': pos_counts['TE'],
            'qb_count': pos_counts['QB'],
            'balance_issues': balance_issues,
            'rb_quality': round(rb_quality, 1),
            'wr_quality': round(wr_quality, 1),
            'te_quality': round(te_quality, 1),
            'qb_quality': round(qb_quality, 1),
            'archetype': archetype,
            'recommended_next': rec_pos,
            'needs': dict(needs)
        }


def load_draft_pool(path: str) -> List[Player]:
    with open(path, 'r') as f:
        data = json.load(f)
    return [Player(**p) for p in data]


if __name__ == '__main__':
    # Demo
    players = load_draft_pool('/Users/benbrackett/draft-engine/data/draft_pool.json')
    config = DraftConfig()
    state = DraftState(config, players[:200], {})
    
    engine = ValuationEngine(state)
    
    print("=== DRAFT ENGINE DEMO ===")
    print(f"Teams: {config.teams}, Roster spots: {config.roster_spots}")
    print(f"Replacement levels: {engine._replacement_values}")
    print(f"\nPositional scarcity:")
    for pos in ['QB', 'RB', 'WR', 'TE']:
        print(f"  {pos}: {engine.positional_scarcity(pos):.2f}")
    
    print(f"\n=== TOP 10 RECOMMENDATIONS FOR TEAM 0 ===")
    recs = engine.get_recommendations(0, 10)
    for i, r in enumerate(recs, 1):
        p = r['player']
        print(f"{i}. {p.name} ({p.position}) - Score: {r['total_score']}, VORP: {r['vorp']}, Scarcity: {r['scarcity']}")
