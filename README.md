# Front Office History

Historical NFL GM / owner simulator, 2010–2026.

## Design contract
The current visual design is frozen. Data/engine work must not redesign the interface unless explicitly requested.

## Architecture
The browser never downloads nflverse/ESPN data at runtime. `scripts/build_data.py` downloads and validates historical sources during the build and creates one static JavaScript bundle at `dist/data/offline-data.js`. `scripts/build_site.py` copies the frozen UI into `dist/index.html` and switches its loaders to that bundle.

This removes CORS/file-preview failures and makes roster ordering deterministic.

## Historical snapshot rule
Selecting offseason `Y` represents the club immediately after season `Y-1` and before the main `Y` offseason transaction cycle.

## Roster order rule
Every player is assigned an explicit `room_order` before the site is built. The UI does not calculate WR1/QB1/TE1 itself.

Position rooms are:
QB, RB, FB, WR, TE, OT, G, C, EDGE/DE, DT/NT, LB, CB, S, K, P, LS.

Ordering priorities:
1. official historical depth tier across the completed season;
2. continuity as a starter / backup across official depth-chart snapshots;
3. within the same tier, actual season role/usage and starts;
4. prior-season role only as a final tiebreaker;
5. players with no official depth evidence always follow players with official evidence.

The generated data stores the final sequential order (`room_order: 1, 2, 3...`) and the Roster section displays that exact value.

## Build
```bash
python scripts/build_data.py --years 2010:2026
python scripts/audit_data.py
python scripts/build_site.py
python scripts/smoke_test.py
```

The GitHub Actions workflow runs the same sequence and uploads a publishable `dist/` artifact.

## Accuracy policy
- Never invent a historical player, pick, free-agent status, coach, record, or cap number.
- Never substitute a present-day roster endpoint for a missing historical roster.
- Missing verified facts remain null/unknown.
- Simulation values (trade value, team rating, market offer) are labeled model outputs.
- Historical source data and simulation state never overwrite one another.

## Verified source coverage
- Season rosters: 1920+
- Weekly rosters: 2002+
- Depth charts: 2001+
- Player stats: 1999+
- Snap counts: 2012+

The build skips datasets before their documented coverage start instead of treating those expected gaps as download errors.

## Important 2010 draft-capital note
The nfldata trade table begins on May 1, 2010. That means opening 2010 pick ownership cannot be reconstructed from that table alone with the same confidence as later seasons. The project does not treat that source limitation as verified exact historical ownership.
