"""Validation et agregation stdlib des 80 duels instrumentes."""

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics


def analyze(root: Path) -> dict:
    groups = {}
    paired = {}
    for model in ('v3', 'v4'):
        directory = root / model
        launch = json.loads((directory / 'launch.json').read_text())
        report = json.loads((directory / 'results.json').read_text())
        assert report['completed'] and len(report['results']) == 40
        project = Path(__file__).resolve().parent.parent
        for name, digest in launch['inputs'].items():
            assert hashlib.sha256((project / name).read_bytes()).hexdigest() == digest, name
        for opponent in ('autosub', 'sub15'):
            episodes = [e for e in report['results'] if e['opponent_label'] == opponent]
            assert sorted(e['seed'] for e in episodes) == list(range(98000, 98020))
            counts, damage, first_damage, ammo_used, empty, transitions = (Counter() for _ in range(6))
            events, trace_damage = Counter(), Counter()
            decisions = 0
            for e in episodes:
                paired[model, opponent, e['seed']] = e
                transitions[e['first']['outcome'] + '->' + e['settled']['outcome']] += 1
                counts.update(e['counts'])
                damage.update(e['damage'])
                first_damage.update(e['first']['damage'])
                assert 0 < e['first']['tick'] <= 6000
                assert e['first']['tick'] <= e['settled']['tick'] <= 12000
                assert not e['settled']['pending'] or e['settled']['tick'] == 12000
                for phase in ('first', 'settled'):
                    for pid, stocks in e['initial_ammo'].items():
                        for family, initial in stocks.items():
                            final = e[phase]['ammo'][pid][family]
                            initial = initial if isinstance(initial, dict) else {'count': initial}
                            final = final if isinstance(final, dict) else {'count': final}
                            for kind, value in initial.items():
                                remaining = final[kind]
                                assert 0 <= remaining <= value
                                key = f'{phase}:{pid}:{family}:{kind}'
                                ammo_used[key] += value - remaining
                                empty[key] += int(value > 0 and remaining == 0)
                episode_damage, episode_events, episode_counts = Counter(), Counter(), Counter()
                dead = set()
                with gzip.open(directory / f'{opponent}_{e["seed"]}.jsonl.gz', 'rt') as handle:
                    for line in handle:
                        row = json.loads(line)
                        assert row['seed'] == e['seed']
                        name = row['type']
                        if name == 'RLDecision':
                            assert row['player_id'] not in dead
                            assert row['tick'] < e['settled']['tick']
                            result = row['result']
                            assert not result['weapon_fired'] or row['rejection_reason'] is None
                            assert not result['weapon_requested'] or result['weapon_fired'] or row['rejection_reason']
                            phase = 'first' if row['tick'] < e['first']['tick'] else 'continuation'
                            prefix = f'{phase}:{row["player_id"]}'
                            episode_counts[prefix + ':decisions'] += 1
                            for flag, value in result.items():
                                if value is True:
                                    episode_counts[prefix + ':' + flag] += 1
                            if row['requested_kind']:
                                status = 'fired' if result['weapon_fired'] else row['rejection_reason']
                                episode_counts[f'{prefix}:{row["requested_kind"]}:{row["contact"]}:{status}'] += 1
                            decisions += 1
                        elif name == 'damage':
                            episode_damage[f'{row["attacker_id"]}:{row["weapon"]}:{row["victim_id"]}'] += row['actual']
                        elif name == 'native_launch':
                            phase = 'first' if row['tick'] < e['first']['tick'] else 'continuation'
                            status = 'fired' if row['fired'] else 'rejected'
                            episode_counts[f'{phase}:{row["player_id"]}:native:{row["weapon"]}:{row["contact"]}:{status}'] += 1
                            before = row['ammo_before']['torpedo_ammo'][row['weapon']]
                            after = row['ammo_after']['torpedo_ammo'][row['weapon']]
                            assert before - after == int(row['fired'])
                        elif name == 'first_endpoint':
                            assert row['data'] == e['first']
                            observed = 'loss' if dead == {'bot001'} else 'win' if dead == {'bot002'} else 'draw'
                            assert observed == e['first']['outcome']
                        else:
                            episode_events['event:' + name] += 1
                            if name == 'BoatSunk':
                                dead.add(row['data']['victim_id'])
                assert dict(episode_damage) == e['damage']
                episode_counts.update(episode_events)
                assert dict(episode_counts) == e['counts']
                assert dict(episode_events) == {k: v for k, v in e['counts'].items() if k.startswith('event:')}
                observed = 'loss' if dead == {'bot001'} else 'win' if dead == {'bot002'} else 'draw'
                assert observed == e['settled']['outcome']
                trace_damage.update(episode_damage)
                events.update(episode_events)
            assert damage == trace_damage
            first = Counter(e['first']['outcome'] for e in episodes)
            settled = Counter(e['settled']['outcome'] for e in episodes)
            groups[f'{model}/{opponent}'] = {
                'matches': 20, 'first': dict(first), 'settled': dict(settled),
                'transitions': dict(transitions), 'counts': dict(counts),
                'damage': dict(damage), 'first_damage': dict(first_damage),
                'ammo_used': dict(ammo_used), 'empty_episodes': dict(empty),
                'decisions_checked': decisions,
                'continued': sum(e['settled']['tick'] > e['first']['tick'] for e in episodes),
                'settling_capped': sum(bool(e['settled']['pending']) for e in episodes),
                'extra_seconds': sum((e['settled']['tick'] - e['first']['tick']) * .05 for e in episodes),
                'mean_first_seconds': statistics.mean(e['first']['tick'] * .05 for e in episodes),
            }
    comparisons = {}
    score = {'win': 1, 'draw': .5, 'loss': 0}
    for phase in ('first', 'settled'):
        differences = []
        for seed in range(98000, 98020):
            ds = []
            for opponent in ('autosub', 'sub15'):
                a, b = (paired[m, opponent, seed] for m in ('v3', 'v4'))
                assert a['initial'] == b['initial'], (opponent, seed)
                assert a['initial_ammo'] == b['initial_ammo']
                ds.append(score[b[phase]['outcome']] - score[a[phase]['outcome']])
            differences.append(statistics.mean(ds))
        mean = statistics.mean(differences)
        half = 1.96 * statistics.stdev(differences) / math.sqrt(20)
        comparisons[phase] = {'gain_pp': 100 * mean, 'seed_clustered_ci95_pp':
                              [100 * (mean - half), 100 * (mean + half)]}
    return {'validated_matches': 80, 'groups': groups, 'paired': comparisons}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = analyze(args.directory)
    text = json.dumps(result, indent=2)
    if args.output:
        with args.output.open('x') as handle:
            handle.write(text + '\n')
    print(text)
