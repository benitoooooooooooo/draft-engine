# 2O2 Fantasy Football Draft Engine

A real-time draft assistant that maximizes draft surplus through VORP-based valuations, positional scarcity tracking, and opponent-aware recommendations.

## Quick Start

```bash
cd /Users/benbrackett/draft-engine
python3 src/draft_cli.py
```

## Draft Order (league.json)

`league.json` configures the session — no prompts at launch:

```json
{
  "league_name": "BEEF",
  "teams": 10,
  "qb_slots": 1, "rb_slots": 2, "wr_slots": 2, "te_slots": 1,
  "flex_slots": 1, "k_slots": 1, "dst_slots": 1, "bench_slots": 6,
  "order": ["Phil", "Adam", "Steve", "Jeff", "Ben", "Ricky", "Isaac", "Kevin", "Ric", "Todd"],
  "me": "Ben"
}
```

`order` = snake slots 1..N (slot 1 = picks 1 & 20 in a 10-team 15-round).
`me` = your team name, exact match. Slot changes auto-derive `roster_spots`.
Any name not in the skill pool records as an off-pool placeholder (K/DST),
and bare `pass` records one without guessing a name.

## 2026 Data

`data/draft_pool.json` is built from **FantasyPros consensus ECR** (124 experts,
refreshed daily) × **ffdraft.app 2026 PPR projections** (ESPN+CBS+NFL average),
joined by name with Sleeper IDs. To refresh before a draft:

```bash
python3 scripts/update_pool.py --top 200 --out data/draft_pool_2026.json
cp data/draft_pool_2026.json data/draft_pool.json
```

## Live Agent Coaching

Two channels connect the draft to the Hermes agent:

1. **`src/draft_watch.py`** — read-only companion. Reconstructs the board from
   the CLI's `draft_state.json` export (written on every pick) and answers
   `status | recs | top <pos> | run | need <pos> | compare A B | json`.
   The agent runs this on its own copy while you type picks in your terminal.

2. **`coach_notes.txt`** — the agent writes advice here; the CLI displays it
   as a "📝 COACH NOTES" box right before each pick prompt when it changes.

Session flow: you run `draft_cli.py`, feed it every pick as it happens, and
ping the agent (Telegram/chat) between rounds — it inspects the exported
state, runs `draft_watch.py`, and answers or pushes notes back into your
terminal via the notes file.

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
