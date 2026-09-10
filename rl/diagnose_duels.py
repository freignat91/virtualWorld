"""Duels diagnostiques hors ligne, sans modifier les terminaisons Gym."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import gzip
import json
import math
import os
from pathlib import Path
import subprocess
import tarfile
import time
from typing import Any
from unittest.mock import patch

import numpy as np

from rl.rl_control import apply_action, build_observation, _contact_target
from rl.rl_env import PHYSICS_DT, SubmarineDuelEnv
from rl.rng import preserve_rng_state


ROOT = Path(__file__).resolve().parent.parent
AMMO = ('torpedo_ammo', 'grenade_ammo', 'cannon_ammo', 'lure_ammo', 'mine_ammo', 'drone_ammo')


def ammo_snapshot(env: SubmarineDuelEnv, sid: str) -> dict:
    return {name: json.loads(json.dumps(getattr(env.runner.legacy, name).get(sid)))
            for name in AMMO}


def outcome(alive: list[bool]) -> str:
    return 'win' if alive == [True, False] else 'loss' if alive == [False, True] else 'draw'


def pending_torpedoes(sim: Any, sunk: set[str]) -> list:
    return sorted((t['ownerPlayerId'], t['tid']) for t in sim.torpedoes.values()
                  if t['ownerPlayerId'] in sunk)


def launch_context(bot: dict, sim: Any, action: Any) -> dict:
    """Lecture du contact deja acquis, sans nouvel appel capteur."""
    index = 3 if bot['boatType'] == 'submarine' else 2
    kind = {0: None, 1: 'acoustic', 2: 'autonomous', 3: 'cannon', 4: 'grenade'}[int(action[index])]
    target = _contact_target(bot, sim)
    context = 'blind' if target is None else 'fresh' if target['tracked'] else 'memory'
    reason = None
    if kind:
        cooldown = 'torpedo' if kind in ('acoustic', 'autonomous') else kind
        if sim.now() < bot.get(f'next_{cooldown}_at', 0):
            reason = 'cooldown'
        elif kind in ('cannon', 'grenade') and target is None:
            reason = 'no_contact'
        elif kind == 'cannon' and target['position']['y'] < -(target['boat'].get('flotation', 2)) / 10 - .05:
            reason = 'target_submerged'
        else:
            sid = bot['sid']
            if kind in ('acoustic', 'autonomous'):
                stock = sim._legacy.torpedo_ammo[sid].get(kind, 0)
                limit = bot['boat']['torpedoes'][kind]['maxRangeMeters'] * .7
            elif kind == 'cannon':
                stock = sim._legacy.cannon_ammo[sid]['cannon']
                limit = bot['boat']['cannon']['range']
            else:
                stock = sim._legacy.grenade_ammo[sid]
                limit = bot['boat']['grenade']['rangeMeters']
            distance = (math.hypot(target['position']['x'] - bot['position']['x'],
                                   target['position']['z'] - bot['position']['z']) * 10
                        if target else None)
            # Le canon valide la portee avant le stock, les autres font l'inverse.
            if kind == 'cannon' and (distance == 0 or distance > limit):
                reason = 'range'
            elif stock <= 0:
                reason = 'ammo_empty'
            elif distance is not None and distance > limit:
                reason = 'range'
    return {'requested_kind': kind, 'contact': context,
            'contact_age': sim.now() - target['observed_at'] if target else None,
            'rejection_reason': reason}


@preserve_rng_state()
def duel(env: SubmarineDuelEnv, model: Any, seed: int, emit: Any) -> dict:
    observation, opponent_info = env.reset(seed=seed)
    runner, sim = env.runner, env.runner.sim
    sids = [env.agent_sid, env.opponent_sid]
    ids = [runner.legacy.bots[s]['id'] for s in sids]
    initial_ammo = {pid: ammo_snapshot(env, sid) for pid, sid in zip(ids, sids)}
    last_ammo = dict(initial_ammo)
    initial = {pid: {k: runner.legacy.bots[sid][k] for k in ('position', 'rotation', 'integrity')}
               for pid, sid in zip(ids, sids)}
    initial = json.loads(json.dumps(initial))
    sunk: set[str] = set()
    counts: Counter = Counter()
    damage: Counter = Counter()
    state = None
    first = None
    step = 0
    source = 'unattributed'
    original_damage = sim.bot_apply_damage
    original_sink = sim.sink_bot

    def record(data: dict) -> None:
        emit({'seed': seed, 'tick': step, 'sim_time': runner._time, **data})

    def damaged(sid: str, bot: dict, amount: float, attacker: str) -> None:
        before = bot['integrity']
        original_damage(sid, bot, amount, attacker)
        actual = before - bot['integrity']
        if actual:
            key = f'{attacker}:{source}:{bot["id"]}'
            damage[key] += actual
            record({'type': 'damage', 'weapon': source, 'attacker_id': attacker,
                    'victim_id': bot['id'], 'actual': actual, 'requested': amount})

    def sinking(sid: str, bot: dict, attacker: str) -> None:
        last_ammo[bot['id']] = ammo_snapshot(env, sid)
        original_sink(sid, bot, attacker)

    def wrap(method: Any, weapon: str) -> Any:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            nonlocal source
            previous, source = source, weapon
            try:
                return method(*args, **kwargs)
            finally:
                source = previous
        return wrapped

    def launch_wrap(method: Any, weapon: str) -> Any:
        def wrapped(bot: dict, target: Any = None, *args: Any, **kwargs: Any) -> Any:
            before = ammo_snapshot(env, bot['sid'])
            fired = method(bot, target, *args, **kwargs)
            context = 'blind' if target is None else 'fresh' if target.get('tracked') else 'memory'
            rejection = None if fired else ('ammo_empty' if before['torpedo_ammo'].get(weapon, 0) <= 0 else 'range')
            phase = 'first' if first is None else 'continuation'
            counts[f'{phase}:{bot["id"]}:native:{weapon}:{context}:{"fired" if fired else "rejected"}'] += 1
            record({'type': 'native_launch', 'player_id': bot['id'], 'weapon': weapon,
                    'contact': context, 'target': target, 'fired': fired, 'rejection_reason': rejection,
                    'ammo_before': before, 'ammo_after': ammo_snapshot(env, bot['sid'])})
            return fired
        return wrapped

    from contextlib import ExitStack
    with ExitStack() as stack:
        stack.enter_context(patch.object(sim, 'bot_apply_damage', damaged))
        stack.enter_context(patch.object(sim, 'sink_bot', sinking))
        for method, weapon in (('spawn_bot_torpedo', 'acoustic'),
                               ('spawn_bot_torpedo_autonomous', 'autonomous')):
            stack.enter_context(patch.object(sim, method, launch_wrap(getattr(sim, method), weapon)))
        for method, weapon in (('_explode_torpedo', 'torpedo'),
                               ('explode_server_grenade', 'grenade'),
                               ('explode_server_mine', 'mine'),
                               ('update_cannon_shells', 'cannon')):
            stack.enter_context(patch.object(sim, method, wrap(getattr(sim, method), weapon)))
        while step < 12000:
            for side, sid in enumerate(sids):
                bot = runner.legacy.bots.get(sid)
                policy = model if side == 0 else env._opponent_model
                if bot is None or policy is None:
                    continue
                if side == 0:
                    action, state = policy.predict(observation, state=state,
                        episode_start=np.array([step == 0]), deterministic=True)
                else:
                    observation_o = build_observation(bot, sim, runner.world)
                    action, env._opponent_state = policy.predict(observation_o,
                        state=env._opponent_state,
                        episode_start=np.array([env._opponent_episode_start]), deterministic=True)
                    env._opponent_episode_start = False
                context = launch_context(bot, sim, action)
                result = apply_action(bot, sim, action)
                if result['weapon_fired']:
                    assert context['rejection_reason'] is None, context
                elif result['weapon_requested']:
                    assert context['rejection_reason'] is not None, (context, result)
                pid = ids[side]
                phase = 'first' if first is None else 'continuation'
                counts[f'{phase}:{pid}:decisions'] += 1
                for flag, value in result.items():
                    if value is True:
                        counts[f'{phase}:{pid}:{flag}'] += 1
                if context['requested_kind']:
                    status = 'fired' if result['weapon_fired'] else context['rejection_reason']
                    counts[f'{phase}:{pid}:{context["requested_kind"]}:{context["contact"]}:{status}'] += 1
                record({'type': 'RLDecision', 'player_id': pid,
                        'observation': (observation if side == 0 else observation_o).tolist(),
                        'action': action.tolist(), 'result': result, **context,
                        'ammo': ammo_snapshot(env, sid)})
            for _ in range(env.frame_skip):
                runner.step(PHYSICS_DT)
                step += 1
                for event in sim.drain_events():
                    name = type(event).__name__
                    if name == 'BoatSunk':
                        sunk.add(event.victim_id)
                    if name not in ('PlayerMoved', 'TorpedoState', 'DroneState'):
                        counts[f'event:{name}'] += 1
                        record({'type': name, 'data': asdict(event)})
                for pid, sid in zip(ids, sids):
                    if sid in runner.legacy.bots:
                        last_ammo[pid] = ammo_snapshot(env, sid)
                alive = [sid in runner.legacy.bots for sid in sids]
                assert sunk == {pid for pid, live in zip(ids, alive) if not live}
                if first is None and (sunk or step >= env.max_physics_steps):
                    first = {'outcome': outcome(alive), 'tick': step,
                             'ammo': json.loads(json.dumps(last_ammo)),
                             'damage': dict(damage), 'counts': dict(counts),
                             'pending': pending_torpedoes(sim, sunk)}
                    record({'type': 'first_endpoint', 'data': first})
                if first is not None and (not sunk or not pending_torpedoes(sim, sunk) or step >= 12000):
                    break
                if first is not None and first['tick'] == step:
                    break
            if first is not None and (not sunk or not pending_torpedoes(sim, sunk) or step >= 12000):
                break
            if sids[0] in runner.legacy.bots:
                observation = build_observation(runner.legacy.bots[sids[0]], sim, runner.world)
    assert first is not None
    assert not any(':unattributed:' in k for k in damage), damage
    return {'seed': seed, **opponent_info, 'initial': initial, 'initial_ammo': initial_ammo,
            'first': first, 'settled': {'outcome': outcome(alive), 'tick': step,
            'pending': pending_torpedoes(sim, sunk), 'ammo': last_ammo},
            'counts': dict(counts), 'damage': dict(damage)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    for key in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS'):
        if os.environ.get(key) != '1':
            parser.error(f'{key}=1 requis')
    args.output.mkdir(parents=True, exist_ok=False)
    from sb3_contrib import RecurrentPPO
    from rl.evaluate_ai import artifact_manifest
    config_path = ROOT / 'rl/configs/aidest_v4.json'
    config = json.loads(config_path.read_text())
    pool = ROOT / 'rl/models_rl/aisub_v15_scripted/best'
    assert len(list(pool.glob('*.zip'))) == 1
    paths = set(ROOT.glob('*.py')) | set((ROOT / 'rl').glob('*.py'))
    for directory in ('maps', 'boats', 'bots/ai', 'rl/configs'):
        paths.update((ROOT / directory).glob('*.json'))
    paths.update((args.model.resolve(), *pool.glob('*.zip'), config_path))
    paths.update((ROOT / 'rl/models_rl').glob('*/best/*.zip'))
    manifest = {str(p.relative_to(ROOT)): artifact_manifest(p)['sha256'] for p in sorted(paths)}
    started = time.time()
    launch = {'inputs': manifest, 'model': str(args.model), 'seeds': list(range(98000, 98020)),
              'config': config, 'threads': {k: os.environ[k] for k in
              ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS')},
              'started': started, 'pid': os.getpid(), 'numpy': np.__version__}
    (args.output / 'launch.json').write_text(json.dumps(launch, indent=2))
    for name, command in (('initial.diff', ['git', 'diff']), ('staged.diff', ['git', 'diff', '--cached']),
                          ('status.txt', ['git', 'status', '--short']), ('head.txt', ['git', 'rev-parse', 'HEAD']),
                          ('dependencies.txt', [os.sys.executable, '-m', 'pip', 'freeze'])):
        (args.output / name).write_bytes(subprocess.check_output(command, cwd=ROOT))
    with tarfile.open(args.output / 'sources.tar.gz', 'w:gz') as archive:
        for path in sorted(paths):
            if path.suffix != '.zip':
                archive.add(path, arcname=str(path.relative_to(ROOT)))
    with preserve_rng_state():
        model = RecurrentPPO.load(args.model, device='cpu')
    results = []
    for opponent in ('autosub', 'sub15'):
        options = {k: config['env'][k] for k in ('frame_skip', 'max_physics_steps', 'spawn_min_m', 'spawn_max_m')}
        env = SubmarineDuelEnv(map_name='testCombats', agent_boat_type='destroyer',
            control_version=config['env']['control_version'], reward=config['reward'],
            fixed_opponent_pool_dir=str(pool) if opponent == 'sub15' else None,
            fixed_policy_probability=1.0 if opponent == 'sub15' else 0.0, **options)
        try:
            for seed in range(98000, 98020):
                with gzip.open(args.output / f'{opponent}_{seed}.jsonl.gz', 'wt') as trace:
                    result = duel(env, model, seed, lambda row: trace.write(json.dumps(row) + '\n'))
                result['opponent_label'] = opponent
                results.append(result)
                print(opponent, seed, result['first']['outcome'], result['settled']['outcome'], flush=True)
        finally:
            env.close()
    assert len(results) == 40
    changed = [p for p, digest in manifest.items() if artifact_manifest(ROOT / p)['sha256'] != digest]
    assert not changed, changed
    completion = {'results': results, 'elapsed_seconds': time.time() - started,
                  'inputs_unchanged': len(manifest), 'completed': True}
    (args.output / 'results.json').write_text(json.dumps(completion, indent=2))
    print(json.dumps({'completed': True, 'matches': len(results), 'hashes': len(manifest)}))


if __name__ == '__main__':
    main()
