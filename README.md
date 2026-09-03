# 2O2 Fantasy Football Draft Engine

A real-time draft assistant that maximizes draft surplus through VORP-based valuations, positional scarcity tracking, and opponent-aware recommendations.

## Quick Start

```bash
cd /Users/benbrackett/draft-engine
python3 src/draft_cli.py
```

## Features

- **Dynamic VORP**: Value Over Replacement Player recalculates after every pick
- **Positional Scarcity**: Real-time cliff detection (RB run coming? TE wasteland approaching?)
- **Opponent Pressure**: Knows when opponents need your target position
- **Roster Construction Analysis**: Identifies your draft archetype (Zero RB, Elite TE Anchor, etc.)
- **Drop-off Risk**: Tells you which players won't make it back to your next pick
- **Positional Run Alerts**: Flags when a position is being drafted heavily

## Commands During Draft

| Command | Action |
|---------|--------|
| `pick <name>` or just `<name>` | You draft a player |
| `opponent <name>` or `o <name>` | Record opponent's pick |
| `rb`, `wr`, `te`, `qb` | Show top available at position |
| `recs` or `r` | Show your recommendations |
| `roster` or `r` | Show your roster + quality scores |
| `board` or `b` | Show recent picks |
| `all` | Show top available at all positions |
| `help` or `h` | Show commands |
| `quit` or `q` | Exit |

## Recommendation Notes

- **"OPPONENTS NEED THIS"** — Multiple opponents need this position, they'll likely draft it before your next turn
- **"WON'T MAKE IT BACK"** — This player won't be available at your next pick
- **"POSITION CLIFF"** — The drop-off after this player is severe
- **"FILL NEED"** — This addresses a roster gap

## Draft Strategy Tips

1. **Early rounds (1-3)**: Focus on VORP + scarcity. The engine will flag elite TEs and bell-cow RBs.
2. **Middle rounds (4-8)**: Watch for positional runs. The engine alerts when RBs or WRs are flying off the board.
3. **Late rounds (9-16)**: Fill needs + upside. The engine prioritizes handcuffs and high-ceiling WRs.

## Data

Player projections are based on 2025 consensus rankings. Update `data/draft_pool.json` with your own projections if you have preferred sources.

## Files

- `src/engine.py` — Core valuation and draft logic
- `src/draft_cli.py` — Live draft interface
- `data/draft_pool.json` — Player database
