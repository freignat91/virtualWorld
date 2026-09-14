"""Controle local de la campagne v4/v5, sans lancer de duel."""

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import tarfile

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / 'rl/models_rl/aidest_v5_scripted_seed1542/evaluation/diagnostic80_130000'
MODELS = {
    'v4': ('aidest_v4_scripted/best/best_model.zip',
           '90c08a62b551f77f23a90194bb7876841df7cf7a9c50987141c3257aa16ca8e2'),
    'v5': ('aidest_v5_scripted_seed1542/best/best_model.zip',
           '1af86f9b3f1be7235be4a8994ebbfd8e538d0935c078358dfd1ea8374fe8e9de'),
    'sub15': ('aisub_v15_scripted/best/best_model.zip',
              '2849f0c79a15fced51a249720bd25bd4210ee1bafc4c71f79aa942dfaab421c5'),
}


def verify(preflight: bool) -> dict:
    config = json.loads((ROOT / 'rl/configs/aidest_v5.json').read_text())
    v4 = json.loads((ROOT / 'rl/configs/aidest_v4.json').read_text())
    for key in ('env', 'reward', 'model', 'evaluation'):
        assert config[key] == v4[key], key
    for path, expected in MODELS.values():
        assert hashlib.sha256((ROOT / 'rl/models_rl' / path).read_bytes()).hexdigest() == expected
    seeds = set(range(130000, 130020))
    for start, count in ((101542, 30), (110000, 100), (120000, 100), (98000, 20),
                         (96000, 100), (97000, 100)):
        assert seeds.isdisjoint(range(start, start + count))
    if preflight:
        assert not ARCHIVE.exists()
        return {'preflight': True, 'models': MODELS, 'seeds': sorted(seeds)}
    from rl.analyze_duel_diagnostics import analyze
    analysis = analyze(ARCHIVE, ('v4', 'v5'), 130000)
    metrics, episodes, manifests = {}, {}, {}
    for model in ('v4', 'v5'):
        directory = ARCHIVE / model
        launch = json.loads((directory / 'launch.json').read_text())
        report = json.loads((directory / 'results.json').read_text())
        assert Path(launch['model']).resolve() == ROOT / 'rl/models_rl' / MODELS[model][0]
        assert launch['config'] == config
        assert set(launch['threads'].values()) == {'1'}
        assert report['inputs_unchanged'] == len(launch['inputs'])
        with tarfile.open(directory / 'sources.tar.gz') as archive:
            expected = {p: h for p, h in launch['inputs'].items() if not p.endswith('.zip')}
            expected.update(launch['documents'])
            assert set(archive.getnames()) == set(expected)
            for path, digest in expected.items():
                assert hashlib.sha256(archive.extractfile(path).read()).hexdigest() == digest
        manifests[model] = {'inputs': len(launch['inputs']), 'source_files':
                            sum(not p.endswith('.zip') for p in launch['inputs']),
                            'documents': len(launch['documents']), 'elapsed': report['elapsed_seconds'],
                            'pid': launch['pid']}
        episodes[model] = report['results']
        for e in report['results']:
            assert set(e['initial']) == {'bot001', 'bot002'}
            assert e['initial']['bot001']['integrity'] == 200
            assert e['initial']['bot002']['integrity'] == 100
            if e['opponent_label'] == 'sub15':
                assert e['opponent'] == 'policy:submarine/best_model.zip'
                assert e['opponent_kind'] == 'policy'
                assert launch['inputs']['rl/models_rl/' + MODELS['sub15'][0]] == MODELS['sub15'][1]
            else:
                assert e['opponent'] == 'bt:submarine/autosub'
                assert e['opponent_kind'] == 'bt' and e['opponent_ai'] == 'autosub'
            first_damage = Counter()
            with gzip.open(directory / f'{e["opponent_label"]}_{e["seed"]}.jsonl.gz', 'rt') as trace:
                for line in trace:
                    row = json.loads(line)
                    if row['type'] == 'first_endpoint':
                        assert dict(first_damage) == e['first']['damage']
                        break
                    if row['type'] == 'damage':
                        first_damage[f'{row["attacker_id"]}:{row["weapon"]}:{row["victim_id"]}'] += row['actual']
        for opponent in ('autosub', 'sub15', 'all'):
            es = [e for e in episodes[model] if opponent == 'all' or e['opponent_label'] == opponent]
            result = {'matches': len(es), 'phases': {}, 'changes': [
                {'seed': e['seed'], 'opponent': e['opponent_label'], 'first': e['first']['outcome'],
                 'settled': e['settled']['outcome']} for e in es if e['first']['outcome'] != e['settled']['outcome']],
                'continued': sum(e['settled']['tick'] > e['first']['tick'] for e in es),
                'max_extra_seconds': max((e['settled']['tick'] - e['first']['tick']) * .05 for e in es)}
            for phase in ('first', 'settled'):
                counts, damage, used, empty = (Counter() for _ in range(4))
                wld = Counter(e[phase]['outcome'] for e in es)
                for e in es:
                    counts.update(e['first']['counts'] if phase == 'first' else e['counts'])
                    damage.update(e['first']['damage'] if phase == 'first' else e['damage'])
                    for pid, stocks in e['initial_ammo'].items():
                        for family, initial in stocks.items():
                            final = e[phase]['ammo'][pid][family]
                            initial = initial if isinstance(initial, dict) else {'count': initial}
                            final = final if isinstance(final, dict) else {'count': final}
                            for kind, value in initial.items():
                                key = f'{pid}:{family}:{kind}'
                                used[key] += value - final[kind]
                                empty[key] += int(value > 0 and final[kind] == 0)
                sides = {}
                for pid, enemy in (('bot001', 'bot002'), ('bot002', 'bot001')):
                    launches, refusals = Counter(), Counter()
                    for key, value in counts.items():
                        parts = key.split(':')
                        if len(parts) >= 4 and parts[1] == pid:
                            if len(parts) == 6 and parts[2] == 'native' and parts[-1] == 'fired':
                                launches[parts[4]] += value
                            if len(parts) == 5 and parts[-1] != 'fired':
                                refusals[parts[-1]] += value
                    hull = {weapon: damage[f'{pid}:{weapon}:{enemy}']
                            for weapon in ('torpedo', 'grenade', 'cannon', 'mine')}
                    torpedoes = sum(launches.values())
                    assert torpedoes == sum(used[f'{pid}:torpedo_ammo:{k}'] for k in ('acoustic', 'autonomous'))
                    sides[pid] = {'hull_damage': hull, 'hull_total': sum(hull.values()),
                        'self_damage': sum(v for k, v in damage.items() if k.split(':')[0] == pid == k.split(':')[-1]),
                        'torpedoes': torpedoes, 'launch_context': dict(launches),
                        'blind_pct': 100 * launches['blind'] / torpedoes if torpedoes else None,
                        'torpedo_hull_per_launch': hull['torpedo'] / torpedoes if torpedoes else None,
                        'torpedoes_per_hull_hp': torpedoes / hull['torpedo'] if hull['torpedo'] else None,
                        'grenade_hull_per_launch': hull['grenade'] / used[f'{pid}:grenade_ammo:count']
                            if used[f'{pid}:grenade_ammo:count'] else None,
                        'rejections': dict(refusals),
                        'flags': {flag: sum(v for k, v in counts.items() if k in
                            (f'first:{pid}:{flag}', f'continuation:{pid}:{flag}')) for flag in
                            ('decisions', 'weapon_requested', 'weapon_fired', 'weapon_invalid',
                             'lure_invalid', 'sonar_invalid', 'mine_invalid')}}
                result['phases'][phase] = {'wld': dict(wld),
                    'score_pct': 100 * (wld['win'] + .5 * wld['draw']) / len(es),
                    'sides': sides, 'ammo_used': dict(used), 'empty': dict(empty),
                    'mean_seconds': statistics.mean(e[phase]['tick'] * .05 for e in es)}
            metrics[f'{model}/{opponent}'] = result
    comparisons = {}
    for opponent in ('autosub', 'sub15'):
        for phase in ('first', 'settled'):
            score = {'win': 1, 'draw': .5, 'loss': 0}
            pairs = {m: {e['seed']: e for e in episodes[m] if e['opponent_label'] == opponent} for m in episodes}
            ds = [score[pairs['v5'][s][phase]['outcome']] - score[pairs['v4'][s][phase]['outcome']] for s in sorted(seeds)]
            mean = statistics.mean(ds)
            half = 1.96 * statistics.stdev(ds) / math.sqrt(20)
            comparisons[f'{opponent}/{phase}'] = [100 * mean, 100 * (mean - half), 100 * (mean + half)]
    return {'analysis': analysis, 'metrics': metrics, 'per_opponent_ci': comparisons, 'manifests': manifests}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify(args.preflight)
    text = json.dumps(result, indent=2)
    if args.output:
        with args.output.open('x') as handle:
            handle.write(text + '\n')
    print(text)
