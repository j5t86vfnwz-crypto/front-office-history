#!/usr/bin/env python3
"""Hard audit the exact published depth-chart overlay.

The point of this audit is source fidelity, not normalizing the source into our own
idea of what a depth chart should look like. Published ranks may occasionally skip
a number or use an unusual formation. That is valid source data and must be kept.

For every team/season this verifies:
- a dated/provider-labelled source snapshot exists;
- every published slot/player has a positive source rank;
- player identities are not duplicated inside a single source slot;
- published players resolve to that team's roster;
- the roster carries an exact matching slot/rank/slot-order entry;
- generated slot ordering is deterministic and complete;
- all 32 teams are covered for every selected season.
"""
import argparse
import json
from pathlib import Path


def norm(x):
    return ''.join(c for c in str(x or '').lower() if c.isalnum())


def parse_years(spec):
    if ':' in spec:
        lo, hi = map(int, spec.split(':', 1))
        return list(range(lo, hi + 1))
    return [int(x) for x in spec.split(',') if x.strip()]


def player_identity(item):
    return str(item.get('gsis_id') or item.get('espn_id') or norm(item.get('name')))


def roster_indexes(roster):
    by_gsis = {}
    by_espn = {}
    by_name = {}
    for player in roster:
        if player.get('gsis_id'):
            by_gsis[str(player['gsis_id'])] = player
        if player.get('espn_id'):
            by_espn[str(player['espn_id'])] = player
        for value in (player.get('full_name'), player.get('display_name'), player.get('player_name')):
            key = norm(value)
            if key:
                by_name.setdefault(key, player)
    return by_gsis, by_espn, by_name


def resolve_roster_player(item, indexes):
    by_gsis, by_espn, by_name = indexes
    if item.get('gsis_id') and str(item['gsis_id']) in by_gsis:
        return by_gsis[str(item['gsis_id'])]
    if item.get('espn_id') and str(item['espn_id']) in by_espn:
        return by_espn[str(item['espn_id'])]
    return by_name.get(norm(item.get('name')))


def matching_entry(player, slot, depth, slot_order):
    for entry in player.get('published_depth_entries') or []:
        if (
            str(entry.get('slot') or '') == str(slot or '')
            and int(entry.get('depth') or 0) == int(depth)
            and int(entry.get('slot_order') or 0) == int(slot_order)
        ):
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', required=True)
    ap.add_argument('--years', default='2010:2026')
    args = ap.parse_args()

    years = parse_years(args.years)
    bundle = json.loads(Path(args.file).read_text(encoding='utf-8'))
    errors = []
    checks = 0
    packs = 0

    meta = bundle.get('publishedDepthCharts') or {}
    checks += 2
    if int(meta.get('version') or 0) < 2:
        errors.append('bundle missing publishedDepthCharts version 2 metadata')
    if int(meta.get('teamPacksApplied') or 0) != len(years) * 32:
        errors.append(
            f"bundle metadata reports {meta.get('teamPacksApplied')} published-depth packs; "
            f"expected {len(years) * 32}"
        )

    for year in years:
        year_data = (bundle.get('years') or {}).get(str(year)) or {}
        teams = year_data.get('teams') or {}
        if len(teams) != 32:
            errors.append(f'{year}: expected 32 team packs, found {len(teams)}')

        for team, team_data in teams.items():
            packs += 1
            slots = team_data.get('publishedDepthSlots') or []
            provider = team_data.get('publishedDepthProvider')
            snapshot = team_data.get('publishedDepthSnapshot')
            source = team_data.get('publishedDepthSource')
            checks += 5

            if not slots:
                errors.append(f'{year} {team}: no published depth slots')
                continue
            if not provider or not snapshot or not source:
                errors.append(f'{year} {team}: missing published source metadata')
            expected_provider = 'ESPN via nflverse' if year >= 2025 else 'NFL Data Exchange via nflverse'
            if provider != expected_provider:
                errors.append(f'{year} {team}: provider {provider!r} != {expected_provider!r}')
            if int(team_data.get('rosterSeason') or 0) != year:
                errors.append(f"{year} {team}: rosterSeason={team_data.get('rosterSeason')}, expected {year}")

            roster = team_data.get('roster') or []
            indexes = roster_indexes(roster)
            slot_orders = []
            entries = 0

            for slot_row in slots:
                label = str(slot_row.get('slot') or '')
                slot_order = int(slot_row.get('slot_order') or 0)
                players = slot_row.get('players') or []
                slot_orders.append(slot_order)
                checks += 3

                if not label:
                    errors.append(f'{year} {team}: blank published slot label')
                if slot_order < 1:
                    errors.append(f'{year} {team} {label}: invalid slot_order {slot_order}')

                seen_identities = set()
                previous_depth = None
                for item in players:
                    entries += 1
                    depth = int(item.get('depth') or 0)
                    identity = player_identity(item)
                    checks += 5

                    if not item.get('name'):
                        errors.append(f'{year} {team} {label}: blank published player')
                    if depth < 1:
                        errors.append(f"{year} {team} {label} {item.get('name')}: invalid source depth {depth}")
                    if identity in seen_identities:
                        errors.append(f"{year} {team} {label}: duplicate source identity {item.get('name')}")
                    seen_identities.add(identity)

                    # We preserve gaps from the source, but the copied table must remain
                    # in the source's nondecreasing depth-rank order.
                    if previous_depth is not None and depth < previous_depth:
                        errors.append(
                            f'{year} {team} {label}: source ranks out of order '
                            f'({previous_depth} then {depth})'
                        )
                    previous_depth = depth

                    roster_player = resolve_roster_player(item, indexes)
                    if roster_player is None:
                        errors.append(f"{year} {team} {label}: {item.get('name')} missing from roster")
                        continue
                    if not matching_entry(roster_player, label, depth, slot_order):
                        errors.append(
                            f"{year} {team} {label}: {item.get('name')} source depth {depth} "
                            'does not match roster published_depth_entries'
                        )

            if sorted(slot_orders) != list(range(1, len(slot_orders) + 1)):
                errors.append(f'{year} {team}: slot_order is not sequential 1..{len(slot_orders)}')
            if len(slots) < 10 or entries < 20:
                errors.append(f'{year} {team}: snapshot too small ({len(slots)} slots/{entries} entries)')

    expected = len(years) * 32
    if packs != expected:
        errors.append(f'coverage {packs}/{expected} team-year packs')

    print(f'EXACT DEPTH AUDIT: {checks:,} checks; {packs}/{expected} packs; {len(errors)} errors')
    for error in errors[:250]:
        print('ERROR', error)
    if len(errors) > 250:
        print(f'ERROR ... {len(errors) - 250} more')
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
