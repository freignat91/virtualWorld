
# Delegation
- Work directly by default.
- Do not spawn subagents/workers for tasks you can reasonably perform yourself.
- Do not delegate a sequential task merely to wait for the worker's result.
- Delegate only when there is meaningful parallelism or a clear quality benefit.
- Use the minimum number of workers necessary.
- Default worker count: 0.

# Doc
-  Do not update documentation, only when i ask to do so

# Efficiency guidelines

Optimize for compute and usage efficiency.

## Delegation
- Work directly by default.
- Do not spawn subagents/workers for tasks you can reasonably perform yourself.
- Do not delegate a sequential task merely to wait for the worker's result.
- Delegate only when there is meaningful parallelism or a clear quality benefit.
- Use the minimum number of workers necessary.
- Default worker count: 0, subagent/worker can be used to launch RL training at least

## Verification
- Match testing effort to the size and risk of the change.
- Do not add or run broad test suites for trivial, reversible changes.
- Run the smallest relevant verification first.
- If relevant checks pass, do not repeatedly rerun them without a reason.

# AI Bots — Architecture, Training, Invariants and Evaluation

Latest mobility runtime v17 is FINAL, OFFICIAL and READ-ONLY as of2026-09-14.
Public aliases are aisub_mobility_runtime_v17/aidest_mobility_runtime_v17;
isolated code and manifests live under bot_versions/v17, with physical best-model
copies. Both deterministic20-route validations reach100% arrival/open/obstacle,
0 sunk/stuck and no weapon/lure/sonar requests. Submarine passes every gate.
Destroyer has one explicitly accepted residual failure:1/20 coastal graze,
3.65/200HP; all other gates pass. Final/intermediate radii are500m; long routes
prefer safe axis-aligned points, then shortest safe near-axis candidates, then
segmented Dijkstra fallback, with every exposed segment<=7.5km. Movement training
and runtime iteration are closed: do not modify/retrain/replace/promote v17 code,
manifests or weights. V16 remains unchanged/read-only. Next planned phase is
combat v18, not prepared or launched. See TRAINING_RL.md. Supersedes every older
mobility ACTIVE/next-step status.

Latest mobility runtime v8 pilots ACTIVE at2026-09-12 15:58+02: simultaneous
fresh CUDA100k destroyer PID533844 seed77542 and submarine PID533854 seed78542.
Both verified8192 rollout steps at429/424FPS. Straightness now uses only segments
with positive actual speed: norm of cumulative forward displacement divided by
forward path length; no forward segment yields0. Reverse remains separate and
cannot produce straightness1. Other v7 rewards/interfaces/architecture/gates
unchanged. Config SHAsdc67bd8c.../ba1a58f8....41 targeted tests/JSON/compile/
diff-check pass. Do not duplicate/kill/extend; no auto promotion/continuation/
live/deploy/commit. See TRAINING_RL.md.

Latest mobility runtime v7 pilots COMPLETE: simultaneous fresh runs finished
106496 steps, no process. Distance reward now applies only at positive actual
speed; beyond100m reverse penalty increases-0.03->-0.05/m. Destroyer selected
100k:100% completion,0 coastal/sunk/stuck,straightness1.0,speed0.346,reverse
99.909%,requests0. Submarine selected25k:100% completion,1% coastal,0 sunk/stuck,
straightness1.0,speed0.347,reverse100%,requests0. Both fail speed/reverse; no
best/promotion/continuation/live/deploy/commit. Candidate SHAs4a536f3b.../
afc90b2a..., finals75d2a080.../aa1aff3c.... Prior40 targeted tests pass. See
TRAINING_RL.md.

Latest mobility runtime v6 pilots COMPLETE: simultaneous fresh runs finished
106496 steps in16m34/9m47, exit0/no process. Completion gates are replaced by
sunk_count<=0 and stuck_count<=2; straightness gate50%. Destroyer selected100k:
100% completion/open/obstacle,1% coastal,0 sunk/stuck,0.415% stationary,
straightness0.963 but speed0.346 and reverse100%; fails speed/reverse, candidate
SHA226c57cc..., final28e45ae8.... Submarine selected25k and remains identical at
all evaluations:0 completion/sunk,100 stuck/stationary,speed/straightness0,
weapon/lure/sonar0; fails speed/straightness/stuck/stationary, candidate
SHA6508d2cb..., finald2d71718.... No best/promotion/continuation/live/deploy/
commit.39 targeted tests/JSON/compile/diff-check pass. See TRAINING_RL.md.

Latest mobility runtime v5 pilots COMPLETE: simultaneous fresh runs finished
106496 steps in18m22/18m28, exit0/no process. Destroyer selected75k:71%
completion,42% obstacle,37% coastal,29% stuck,5.642% stationary,speed0.596,
straightness1.0,lure27.233%; fails completion/obstacle/speed/coastal/stuck/
stationary/lure, candidate SHAdae7ff45..., final4ccb5a44.... Submarine selected
50k:99% completion,98% obstacle,1% coastal/stuck,0.562% stationary,speed0.971,
straightness0.087,weapon/lure/sonar0; fails only straightness, candidate
SHAc7e439a1..., final6dc51508.... No best/promotion/continuation/live/deploy/
commit. Prior319 full/16 mobility tests pass; archives and diff-check clean. See
TRAINING_RL.md. Preserves completed v4/v3/v2 results.

Latest mobility runtime v4 pilots COMPLETE: sequential fresh runs finished106496
steps in about20m54 destroyer/22m24 submarine; inherited destroyer PID508240 ended
naturally and launched submarine PID511325 exited0, with no process left. Destroyer
selected75k:100% completion/open/obstacle,0 coastal/stuck,stationary0.415%, speed
0.968, straightness0.084, weapon/sonar0 but lure100%; failures straightness/lure,
candidate SHAef28666f..., final b52a7a43.... Submarine selected75k:100%
completion/open/obstacle,0 coastal/stuck,stationary0.415%, speed0.639,
straightness0.494, weapon/lure/sonar0; failures speed/straightness, candidate
SHA6430d2f7..., final bc160e74.... No best/promotion/continuation/live/deploy/
commit. Prior319 tests were not rerun; final archives validate and diff-check is
clean. See TRAINING_RL.md. Preserves completed v3/v2 results.

Latest mobility runtime v3 pilots COMPLETE: fresh separate runs finished106496
steps in19m44 destroyer/19m27 submarine, exit0/no process. Destroyer selected100k:
98% completion,96% obstacle,2% coastal,2% stuck,speed0.961,straightness0.173,
weapon0 but lure requests100%; candidate SHA7866069d..., final206624cb....
Submarine selected25k:100% completion,0 coastal/stuck,speed0.639,straightness0.092,
weapon/lure/sonar0; candidate SHA9bc636c1.... Its100k improves straightness0.328
but has99% completion,1% coastal/stuck,speed0.638; final SHAb00fd1b1.... All gates
fail; no best/promotion/continuation/live/deploy/commit. Prior61 targeted and14
final mobility tests pass; diff-check clean. See TRAINING_RL.md. Supersedes its
ACTIVE state, not v2 or navigation.

Latest mobility runtime v2 pilots COMPLETE: fresh separate destroyer/submarine
runs finished106496 steps in19m34/17m10, exit0/no process. The -0.1 no-target
penalty eliminates weapon requests in both held-out100 evaluations. Destroyer:
100% completion,0 coastal/stuck,stationary0.415%, speed0.637, straightness0.084,
but lure requests100%. Submarine:99% completion,2% coastal,1% stuck,stationary
0.714%, speed0.967, straightness0.100, lure requests100%. Both fail straightness/
lure gates; destroyer also speed, submarine also zero-coastal. No best/promotion/
continuation/live/deploy/commit. Finals SHAs e2609d1b.../93584800..., selected100k
candidates distinct. Prior315 full and38 targeted tests pass; diff-check clean.
See TRAINING_RL.md. Supersedes its prior ACTIVE state, not v3 or navigation.

Latest goal-oriented shield diagnostic COMPLETE: same50 routes, zero coastal but
destroyer94% arrival/4% stuck/2% timeout/1.256% interventions and submarine92%
arrival/8% stuck/0 timeout/2.431% interventions. Both regress versus closest-safe;
no50k adaptation/training/best/promotion. Reports SHAsa7fa133d.../f5d5c9db....
Default-off navigation shield restored to closest-safe SHA2e17c9c5.... Prior302
full and2 targeted post-restore tests pass; diff-check clean, no process. See
NAVIGATION_CURRICULUM.md. Supersedes only the proposed next-navigation step.

Latest lookahead/shield diagnostics COMPLETE, no training. Optional navigation_v3
previews next waypoint150m destroyer/100m submarine with unchanged13 obs/2
actions. Paired50 control/v3 outcomes are identical: destroyer96% arrival,6%
coastal,2% stuck/timeout; submarine96% arrival,10% coastal,4% stuck,0 timeout.
Optional navigation-only predictive shield50m/5s, default off, eliminates all
coastal damage but yields destroyer96% arrival/4% timeout and submarine94%
arrival/6% stuck. Adaptation criterion fails both; no best/promotion/live/deploy/
commit. Closest-shield report SHAsce1f9119.../5c42bf79....302 tests pass/
156.185s, diff-check clean, no process. See NAVIGATION_CURRICULUM.md. Supersedes
only the next-navigation state below.

Latest aligned-navigation experiment COMPLETE: separate75k runs finished81920
steps in1h00m48/53m59, no process. Progress/initial path/efficiency use the same
50m-clearance route as guidance; route acceptance, obs13/actions2, coefficients
and gates stay unchanged. Selected25k destroyer:91% arrival,6% coastal,4% stuck,
5% timeout,1.070 efficiency, quality0.7521; submarine:98% arrival,2% coastal,2%
stuck,0 timeout,0.991 efficiency, quality0.9396. Candidate SHAsb3c0be56.../
627b147a.... Destroyer regresses; submarine fails only zero-coastal. Fresh100
submarine seed552542 confirms98% arrival,3% coastal,2% stuck,0 timeout,0.413%
stationary and1.032 efficiency; only zero-coastal fails. Report SHA5db07271....
No best, continuation, multi-island, live, deploy or commit.299 tests pass/
146.065s and diff-check clean. See NAVIGATION_CURRICULUM.md. Supersedes ACTIVE
below.

Latest clearance100 navigation experiment COMPLETE: separate hull warm-starts
finished106496 steps in1h26m31/1h23m15, no process. Only guidance clearance
changed50->100m. Best internal destroyer75k:96% arrival,9% coastal,4% stuck,
0 timeout,0.971% stationary,1.086 efficiency, quality0.8204; submarine50k:97%
arrival,6% coastal,3% stuck,0 timeout,0.601% stationary,1.049 efficiency,
quality0.8745. Candidate SHAs2a251964.../b0f66ba3.... All gates fail and no
improvement over safe50 is established; no best/fresh100/final500/multi-island/
continuation/live/deploy/commit. Three targeted tests/prior298 full pass and
diff-check clean. See NAVIGATION_CURRICULUM.md. Supersedes ACTIVE below.

Latest safe-corridor navigation pilots COMPLETE: navigation_v2 keeps a graph
waypoint until direct goal guidance has50m polygon/world clearance. Separate
destroyer/submarine warm-start100k runs select candidates every25k without
relaxing best/ gates. Fresh held-out100 destroyer:97% arrival,4% coastal,2%
stuck,1% timeout,0.470% stationary,1.089 efficiency; submarine:97% arrival,3%
coastal,3% stuck,0 timeout,0.638% stationary,1.003 efficiency. Candidate SHAs
4fd1040e.../2447a9a0.... All gates fail; no best/final500/multi-island/further
continuation/live/deploy/commit. Destroyer100k evaluation was recovered after
the outer wrapper timed out; no process remains.298 tests pass and diff-check is
clean. See NAVIGATION_CURRICULUM.md. Supersedes only the next-navigation choice.

Latest navigation pilot100k COMPLETE: fresh destroyer alone on world, seed11542,
navigation_v1 obs13/action2, no opponents/weapons.106496 steps/19m08 including
100-route deterministic evaluation, exit0/no process. Held-out:5% arrival,44%
coastal-damage episodes,9.248 mean coastal HP,37% stuck,58% timeout,3.976%
stationary,1.245 successful path efficiency. Arrival/coast/stuck gates fail;
stationary/efficiency pass. No best selected. Checkpoint100k SHA6a134069..., final
distinct SHAa7a60018.... Native30m coast damage is now shared humans/bots at1HP/s.
287 tests passed before launch; inputs unchanged. No automatic continuation/live/
promotion/deploy/commit/subagent. See NAVIGATION_CURRICULUM.md.

Latest open-navigation pilot COMPLETE: fresh seed12542,106496 steps/8m17 incl
100 held-out routes, exit0/no process. Results:15% arrival,0 coastal-damage
episodes,4% stuck,81% timeout,1.463% stationary,1.159 successful efficiency.
Coast/stationary/efficiency gates pass; arrival98% and stuck2% fail. No best;
single_island remains blocked and no continuation automatic. Checkpoint100k
SHA3039de40..., final distinct SHA65ff48fa....289 tests before launch; inputs
unchanged. No live/deploy/promotion/commit/subagent. See NAVIGATION_CURRICULUM.md.

Latest behavior pilots COMPLETE: v16/v16b both warm-start untouched v15 best
SHA2849f0c7..., same seed9542/protocol; only unacquired-shot penalty -0.1/-0.5.
Each106496 steps in11m00/10m57, exit0/no process. Same deterministic180 situations:
v15/v16/v16b score33.542/33.958/32.083%, unacquired shots28.081/25.028/15.759%,
misaligned89.067/93.321/90.381%, invalid requests93.143/94.684/93.839%.
Gates5/25/50% fail both; no best or paired-CI claim. v16b checkpoint SHAa4c426bf...
v8 mobility PREPARED but NOT LAUNCHED.278 full tests+config smokes pass. No auto
continuation/live/promotion/deploy/commit/subagent. See BEHAVIOR_PILOTS.md.

Latest V7 FINAL COMPLETE+independent: phase5 ended2026-09-10 22:15:46+02,
106496 new steps/15m14,no process. Internal det34.167%,sampled76.944%.
Independent320 seeds200000-19: phase4/5 settled det42.5/32.5%, sampled75.833/
76.667%; phase5-phase4 det-10[-15.507,-4.493]pp,sampled+0.833[-4.318,5.985]pp,
normal95% CI20 clusters. Phase5 harms standard deterministic runtime with no
established sampled gain.8 jobs exit0,124 hashes/job,320 traces,zero mines/caps.
Recommended NOT promoted: phase4 checkpoint100k SHA9a513b31..., still0W/6L/34D
settled in final deterministic batch. Planned training complete; no continuation/
live/promotion/deploy/commit/subagent. See V7_DEFENSE_PILOT.md; supersedes phase5
ACTIVE below.

Latest authorized V7 phase5 FINAL ACTIVE:2026-09-10 22:00:12+02 PID304338,
run aidest_v7_defense_continue4_seed8542_final100k, CUDA8 workers304358-304365.
Warm-start phase4 checkpoint100k SHA9a513b31..., optimizer loaded, seed8542;
final100k=>106496 new steps. Entropy resumes0.000975 to0.0003; curriculum0.
Verified24576/548FPS finite optimizer;298 inputs/196ZIP unchanged after launch
before docs,15 targeted/prior275 full/prior320 independent duels. Log
/tmp/virtualWorld_aidest_v7_defense_continue4_seed8542_final100k.log. Do not
duplicate/kill/extend; no independent reevaluation/live/promotion/deploy/commit/
subagent. Supersedes phase4 COMPLETE-only block below while preserving its
comparison; see V7_DEFENSE_PILOT.md.

Latest V7 phase4 COMPLETE+independent:106496 new steps/14m29, ended2026-09-10
21:40:29+02, no process. Internal det41.667%,sampled79.722%. Independent320
duels seeds190000-19/autosub/sub15: phase3/4 settled det36.25/45%, sampled
74.167/70.417%; phase4-phase3 +8.75[3.388,14.112]pp det and
-3.75[-8.843,1.343]pp sampled, normal95% CI20 clusters. Det gain supported,
sampled decline uncertain. Zero mines/caps;8 jobs exit0,121 hashes/job,320 traces
validated. No auto continuation/live/promotion/deploy/commit/subagent. Final
planned100k is defensible but requires explicit authorization. See
V7_DEFENSE_PILOT.md; supersedes phase4 ACTIVE below.

Latest authorized V7 phase4 ACTIVE:2026-09-10 21:25:41+02 PID300707,
run aidest_v7_defense_continue3_seed7542_review100k, CUDA8 workers300727-300734.
Warm-start phase3 checkpoint100k SHA3a0438b..., optimizer loaded, seed7542;
remaining phase200k but stop100k=>106496 new steps. Entropy resumes0.00165 to
0.0003 over200k; curriculum0. Verified24576/558FPS finite optimizer;293 inputs/
192ZIP unchanged after launch before docs,15 targeted/prior275 full/prior320
independent duels. Log /tmp/virtualWorld_aidest_v7_defense_continue3_seed7542_review100k.log.
Do not duplicate/kill/auto-continue; no independent reevaluation/live/promotion/
deploy/commit/subagent. Supersedes phase3 COMPLETE-only block below, preserving
its independent comparison; see V7_DEFENSE_PILOT.md.

Latest V7 phase3 COMPLETE + independent comparison:106496 new steps/16m41,
ended2026-09-10 21:06:11+02, no process. Internal det34.167%, sampled73.056%.
Independent320 duels seeds180000-19/autosub/sub15: phase2/phase3 settled det
27.5/35%, sampled72.5/78.333%; paired gains +7.5[0.302,14.698]pp det and
+5.833[0.016,11.650]pp sampled, normal95% CI20 clusters. Sampled invalid weapon
attempts93.817->33.05/duel; zero mines/caps.8 CPU jobs exit0,118 hashes/job,
320 traces validated. Phase3 deterministic still0 wins; no promotion. No auto
continuation/live/deploy/commit/subagent. See V7_DEFENSE_PILOT.md; supersedes
phase3 ACTIVE below. Another100k is defensible but requires explicit choice.

Latest authorized V7 phase3 ACTIVE:2026-09-10 20:49:11+02 PID296452,
run aidest_v7_defense_continue2_seed6542_review100k, CUDA8 workers296472-296479.
Warm-start phase2 checkpoint100k SHAf3148eab..., optimizer loaded, seed6542;
remaining phase300k but stop100k=>106496 new steps. Entropy resumes0.002325 to
0.0003 over300k; completed curriculum disabled. Verified16384/575FPS finite
optimizer;288 inputs/188ZIP unchanged after launch before docs,15 targeted/
prior275 full. Log /tmp/virtualWorld_aidest_v7_defense_continue2_seed6542_review100k.log.
Do not duplicate/kill/auto-continue; no independent eval/live/promotion/deploy/
commit/subagent. Phase2 complete106496/15m20: det33.333%(0W/20L/40D), sampled
81.389%(130W/17L/33D),16721 invalid weapons/no mines. See V7_DEFENSE_PILOT.md;
supersedes phase2 ACTIVE below.

Latest authorized V7 phase2 ACTIVE:2026-09-10 20:28:54+02 PID294428,
run aidest_v7_defense_continue_seed5542_review100k, CUDA8 workers294449-294456.
Warm-start first-pilot checkpoint100k SHA41c5fa5d..., optimizer loaded, seed5542;
new phase400k but stop-after100k =>106496 new steps. Known --resume semantics
reset curriculum/entropy schedules. Verified24576/559FPS and finite optimizer;
283 inputs/184 ZIPs unchanged after startup before docs,15 targeted tests/prior
275 full. Log /tmp/virtualWorld_aidest_v7_defense_continue_seed5542_review100k.log.
Do not duplicate/kill or auto-continue after review; no independent eval/live/
promotion/deploy/commit/subagent. Supersedes COMPLETE-only status below, see
V7_DEFENSE_PILOT.md.

Latest V7 defense pilot COMPLETE:106496 fresh steps/16m14, ended2026-09-10
20:16:10+02, no process. Internal100k deterministic35%(1W/19L/40D,60), sampled
75%(108W/18L/54D,180), sampled autosub80/frozen sub15 70. Zero mines, but29373
sampled invalid weapon attempts; deterministic only11 fires/no lures. Checkpoint
and both selected100k archives share identical policy payload; final106496 is
distinct and unevaluated.273 inputs excluding4 intentional post-launch status
docs and all180 old ZIPs unchanged. No continuation, independent comparison,
promotion/live/deploy/commit/subagent. See V7_DEFENSE_PILOT.md; supersedes ACTIVE
below. Explicit decision required for evaluation versus next training phase.

Latest authorized V7 defense pilot ACTIVE:2026-09-10 19:59:34+02 PID291249,
run aidest_v7_defense_seed4542_review100k. Fresh seed4542 model, no checkpoint,
CUDA8 workers291267-291274; config500k but invocation stop-after100k =>106496
whole-rollout expected. destroyer_duel_v3 obs101/action5/no mine, curriculum20%
completes at review, entropy schedule remains based on500k, dual eval240 matches
at100k. Verified16384steps/492FPS finite optimizer;277 inputs/180 existing ZIPs
unchanged after startup before docs,275 full+7 v3 tests. Archive launch_manifests/
aidest_v7_defense_seed4542_review100k; log /tmp/virtualWorld_aidest_v7_defense_seed4542_review100k.log.
Do not duplicate/kill or auto-continue. No live/promotion/deploy/commit/subagent.
Supersedes PREPARED-only status below, preserving completed V6 evidence.

Latest V7 defense PREPARED, NOT LAUNCHED: user selected6 torpedo+6 lure slots
and removal of RL mines. New destroyer_duel_v3=101 obs, action nvec5 (same shape
as v1, distinct obs): self/contact21, torpedoes6x7, lures6x5,rays8. Torpedoes
use legitimate radar/LOS/thermocline, relative position/velocity,CPA/ETA and
danger ranking; own torpedoes excluded, private type/lock/target hidden. Own
lures remain known, foreign lures require radar visibility; expired excluded.
Old v1/v2 models/runtime remain compatible, but no warm-start into v3. Config
configs/aidest_v7_defense.json plans fresh500k seed4542,dual eval/checkpoints100k;
mine_placed=-1 unreachable safeguard because action/state removed. No training,
production/live/deploy/promotion/commit.275 full tests then7 final v3 targeted
tests pass. See TRAINING_RL.md/TECHNIQUE.md and test_destroyer_v3_observation.py.
This is a combined redesign, not causal
single-variable ablation. Supersedes only the undecided next experiment below.

Latest V6 continuation COMPLETE at507904 new steps,2026-09-10 14:52:31+02,
1h21m43; no process. Internal best deterministic500k=49.167%, sampled100k=
78.611%; final507904 distinct/unselected. Independent400 duels seeds170000-19,
autosub/sub15: settled v4 66.25,v5 80,source500k sampled81.25,continue-det48.75,
continue-sampled70.833%. Continue sampled-source sampled -10.417
[-16.560,-4.274]pp,20 scenario clusters/3 action repeats; self-mine HP
3084.078 vs851.900.10 CPU jobs exit0,107/108 hashes unchanged/job,no600s cap.
Archive models_rl/aidest_v6_continue_seed3542_review500k/evaluation/
independent_170000/. Do not run remaining1.5M automatically or promote/change
runtime. Next experiment requires explicit decision and isolated dimension.
No subagent/live/deploy/commit. Supersedes ACTIVE block below.

Latest authorized V6 continuation ACTIVE:2026-09-10 13:30:32+02:00 PID262667,
aidest_v6_continue_seed3542_review500k from pilot checkpoint500k (not BEST100k).
Budget2M new steps, actual invocation --stop-after-steps500000 for review,
507904 expected after complete rollouts. Seed3542,CUDA,8workers262687-262694;
verified24576steps/421FPS finite optimizer. LR5e-5 constant,entropy0.0003
constant,curriculum0 (already complete),other rules/rewards/architecture same.
Dual selection every100k,240matches/eval, firstdeath300s.13 targeted tests;
270 input/model hashes unchanged after launch before docs,175 existing ZIPs.
Archive models_rl/launch_manifests/aidest_v6_continue_seed3542_review500k/;
log /tmp/virtualWorld_aidest_v6_continue_seed3542_review500k.log.
No coding subagent, no auto continuation beyond review, no live/promotion/
deployment/commit. Latest user authorization supersedes old prepared/no-launch
notes for this phase only; preserve all other work and champions.

Dual checkpoint selection PREPARED, NOT LAUNCHED: optional evaluation key
sampled_action_seed_offsets=[0,1000000,2000000] adds separate sampled callback
and sampled/best artifacts; deterministic best/ remains unchanged. Independent
scores, seeds per episode, no blend or automatic production mode change.
New configs/aidest_v6_dual_eval.json preserves pilot500k and hyperparameters;
old configs/weights intact.267tests pass incl actual tiny CLI training, weighted
repeats, independent best retention/load, RNG and weights invariance.
240 matches/eval at30 episodes/opponent, firstdeath300s (not settling).
See TRAINING_RL.md. No long continuation/live/promotion/deployment/commit.

Latest references160000 COMPLETE on authorization:200 duels,20 scenario seeds
160000-19 x autosub/sub15; v4/v5 deterministic40each,v6checkpoint500k sampled
3 action seeds120total (offset0/1M/2M). Settled81.25/82.5/81.25%; v6-v4
0[-9.627,9.627]pp,v6-v5 -1.25[-9.817,7.317],20 seed clusters with repeats
averaged and covariance retained. No equivalence/superiority proof. All5exit0,
102/103 hashes unchanged/job,262tests. Diagnostic action-seed option only,
no runtime/gameplay/reward/weights change, continuation/live/promotion/commit.
See V6_PILOT_COMPARISON.md; supersedes proposed reference-comparison notes.

V6 mine ablation COMPLETE on explicit user authorization:80 duels seed150000-19,
same500k deterministic checkpoint, control vs agent mine-action forced0 ONLY
in diagnostics; proposed/applied actions retained and validated, opponent intact.
First scores5/40%,settled2.5/40%;gain37.5[27.765,47.235]pp20 seed clusters.
Control32 self-attributed first sinks,5860.019 self-mineHP. No agent mines or
self-mine damage with intervention, but mostly draws and no sonar/grenade/cannon.
Both jobs exit0,103 hashes unchanged each,261tests pass. Gameplay/reward/runtime/
weights unchanged. See V6_PILOT_COMPARISON.md. No continuation,live,promotion,
deployment or commit. Supersedes proposed-not-run mine ablation notes below.

V6 pilot COMPLETE (507904 steps, ~31m30). Comparison140000 COMPLETE:
160 diagnostic duels, BEST100k vs checkpoint500k x deterministic/sampled-agent
x autosub/frozen sub15 x20 seeds140000-140019. Four jobs exit0,102/103 input
hashes unchanged each;259 tests pass. Scores first:51.25/10/81.25/76.25%;
settled53.75/6.25/77.5/77.5%. Late deterministic:32/40 self-attributed sinks
at first endpoint,5886.111 self-mine HP; sampled73.818 self-mine HP.
Only diagnostic --stochastic added, opponent remains deterministic; gameplay,
rewards, standard evaluation/runtime/models unchanged. See V6_PILOT_COMPARISON.md.
Supersedes older ACTIVE status below. No automatic continuation/promotion/live/
commit. Proposed only: frozen late deterministic mine-action ablation, not run.

V6 pilot ACTIVE at2026-09-10T09:09:31+02:00, launch09:08:39, PID244030,
aidest_v6_scripted_seed2542_pilot500k, CUDA RTX5080, workers244048-244055.
Config copies v5 except identity/description/seed2542/total_steps500000.
Actual new_model/source null/resume null/seed2542 verified;258 current tests pass.
First8192 rollout then16384 steps/470 cumulative FPS,8 optimizer updates,
finite logged metrics. Next eval100k/checkpoint250k.99 inputs and58 model hashes
unchanged postlaunch; read-only source/git/SHA/startup evidence under
models_rl/launch_manifests/aidest_v6_scripted_seed2542_pilot500k/.
External admin access resolved prior blocker, no policy change by agent.
Curriculum100k/entropy500k compress vs v5, not an isolated causal comparison.
Do not duplicate/kill healthy job; no promised automatic later monitoring.
See TRAINING_RL.md for actual command/evidence. This authorization supersedes older
no-training notes ONLY for this pilot. No automatic3-5M continuation before
pilot evaluation/report, no live/promotion/deployment/commit/model overwrite.

Latest diagnostic80 COMPLETE (2026-09-10), explicitly authorized: v4best300k/
v5best2M x autosub/sub15 x20 seeds130000-130019,2 CPU single-thread jobs exit0.
First80/78.75%,settled80/77.5%; v5-v4 -1.25[-12.755,10.255] then
-2.5[-13.685,8.685]pp,paired95% normal CI20 seed clusters/40 pairs retaining
covariance.47 continuations,no600s cap;2W->D,1L->D(v5 posthumous grenades).
379/638 torpedoes,79.68/82.60% blind,0.586/0.582 enemy hull HP/launch;
grenades91.78/86.18% offensive damage.99 hashes unchanged/job,81 sources/JSON
+18ZIP and9docs additionally archived;102101 decisions checked,256 tests pass.
Archive models_rl/aidest_v5_scripted_seed1542/evaluation/diagnostic80_130000/.
See DUEL_DIAGNOSTICS.md; supersedes proposed-not-run80 notes below, not1200
independent results. No pooling,causal attribution or equivalence claim.
No next long training justified. Proposed ONLY: frozen-v5 diagnostic blind-shot
ablation,one variable/fresh seeds/separate authorization; NOT run. No gameplay/
reward/config/weights edits,live,promotion,deployment,commit or campaign process
left. CLI seed/config/model parameterization and verification only.

Latest status (2026-09-10): V5 training COMPLETE at03:11:25+02:00 (final ZIP
mtime and complete log),2007040 new steps; BEST selected at2000000,
internal score0.7916666667, SHA256
1af86f9b3f1be7235be4a8994ebbfd8e538d0935c078358dfd1ea8374fe8e9de.
policy_final differs in weights/optimizer as well as7040 steps; not evaluated.
No active train/eval/server process after independent comparison. Supersedes
historical ACTIVE/not-launched notes below; their time-specific instructions
are no longer current. No restart or automatic promotion is authorized here.

Independent110000/120000 COMPLETE:6 CPU single-thread jobs exit0/stderr empty,
1200 validated matches,12 groups100, testCombats, exact aidest_v5 config/reward
(same v4 except identity/seed), autosub and frozen sub15 best. Scores v3/v4best300k/
v5best69.5/80.5/80.375%. V5-v4 -0.125[-3.624,3.374]pp, v5-v3
+10.875[7.036,14.714]pp; paired seed-clustered95% CIs,200 seeds/400 pairs.
V5 incremental +3pp gate vs strongest v4 FAILS; no demonstrated gain over v4,
no equivalence or general robustness claim. V5 fires15.87 torpedoes/duel vs
v4 10.425; acoustic exhaustion147/400 vs26/400; invalid flags68.5425 vs140.1425.
123 launch hashes unchanged after all jobs;256 tests pass, then only five docs
updated. Source training/evaluation executable hashes match; all old ZIPs intact.
Archive: models_rl/aidest_v5_scripted_seed1542/evaluation/independent_110000_120000/.
Details: FAIRNESS_EVALUATION.md/TRAINING_RL.md. First death/300s unchanged,
not autogame settling/600s. Proposed only:80 fresh instrumented v4/v5 duels for
ammo damage/rejections/settling before considering another run; NOT launched.
No gameplay/reward/config/weights edits, retraining, live, deployment, promotion,
existing report overwrite or commit. Historical reports remain separate.

Long training ACTIVE at 2026-09-10T01:10:30+02:00 on explicit latest user
authorization, superseding older agent-only no-launch notes. PID210501,
aidest_v5_scripted_seed1542, CUDA RTX5080, eight forkserver workers210519-210526.
Untouched v4best300k warm-start, actual seed1542/MLP256x256/LSTM256x1 verified
in provenance.json; unchanged config2M new steps. First rollout8192 complete,
24576 steps at523 cumulative FPS after optimizer, finite logged losses/KL.
First eval100k/checkpoint250k pending; training NOT completed, no promotion.
Log /tmp/virtualWorld_aidest_v5_scripted_seed1542.log; immutable/read-only launch
snapshot98 files (including untracked Python) and git/input SHA evidence in
models_rl/launch_manifests/aidest_v5_scripted_seed1542/. All98 launch inputs and
v3/v4/sub15 SHA unchanged at startup.
See TRAINING_RL.md for exact command, full hashes, resources and limitations.
Do not duplicate or kill healthy job; no promised automatic later monitoring,
commit/deploy/live/reward changes or existing checkpoint overwrite.

Warm-start preparation (2026-09-10), NOT a launched long run: aidest_v5.json copies
v4 except identity/description/seed1542; 2M new steps, n_envs8/forkserver unchanged.
Parent remains authorized to launch later, using new aidest_v5_scripted_seed1542
and untouched aidest_v4_scripted/best/best_model.zip (300k). CLI now rejects
nonempty output before writes; --resume means a new phase, not exact continuation.
Native load seed/policy_kwargs enforce seed1542 and exact architecture; existing
GAE buffer sync and callback historical best-score reload are retained. One-time
provenance.json records actual loaded seed/architecture, source hash and versions;
parent still handles code/dirty-worktree/input archival. See TRAINING_RL.md.
CUDA RTX5080 compute verified, torch2.11.0/CUDA13, SB3/contrib2.8.0; no training
throughput claim. Only tiny temporary recurrent tests, no champion overwrite,
long training, live server, commit, deployment or promotion in this preparation.
Validation: 256 tests pass with OMP/MKL/OPENBLAS1, including real eight-worker
forkserver warm-start seeds1542-1549; compile and diff-check pass, source SHA stable.

Diagnostic80 completed (2026-09-10) under newest explicit user authorization,
superseding historical no-evaluation/training notes. v3/v4best300k x autosub/sub15
x20 seeds98000-98019 =80 validated duels, two CPU single-thread exit0 jobs,
79 launch hashes unchanged/job. First scores67.5/76.25%, settled65/73.75%;
four W->D,34 continuations,no600s cap. V4 pre-end432 torpedoes/354blind but
93.79% enemy hull damage from grenades. Existing cooldown penalty flags retained.
No gameplay/reward/config/default end/model edits; diagnostic runner guards dead
controllers and uses real Sim. See DUEL_DIAGNOSTICS.md for evidence/limits.
Parent explicitly authorized for autonomous long training, NOT launched here.
Recommend ONE major dimension warm-start v4best300k instead of v3, ~2M new steps,
seed1542/new run directory, otherwise unchanged v4 scripted config and rewards.
No server/commit/deploy/promotion/model overwrite; dirty STEP1/2/3 preserved.

STEP4 completed (2026-09-10), explicitly authorized after STEP1/2/3, HP200/100/10:
six CPU OMP/MKL/OPENBLAS1 jobs, 1200 validated matches, exact100/opponent/series
96000/97000, testCombats, aidest_v4 config/rewards, autosub and frozen sub15 best.
All exit0/stderr empty, 125 launch hashes unchanged; fresh rules_steps123 archive.
v3/v4 best300k/v4 2M scores 67.00/75.50/66.50%; paired seed-clustered gains
+8.50 [4.727,12.273] and -0.50 [-4.481,3.481] pp (200 seeds,400 pairs).
Reusable analyzer retains cross-opponent covariance; 247 Python tests pass.
v4 300k uses10.3125 torpedoes and147 invalid weapon requests/episode versus
v3 0.3425 and42.245; no blind-shot tags/rejection reasons/attributed damage.
Frozen sub15 observations/actions also affected; suite-specific robustness only.
No old-regime pooling or promotion. Evaluation still first death/300s, NOT
autogame torpedo settling/600s. See FAIRNESS_EVALUATION for WLD/hashes/resources.
Supersedes deferred reevaluation status below; no gameplay/reward/model edits,
training run, deployment, live launch or commit. Next proposed:80 instrumented
v3/v4 duels for ammo/rejection/settling diagnosis before long RL, separately
authorized; human live/network validation and production load still pending.

Step3 targetless torpedo (2026-09-09): RL acoustic/autonomous actions fire without
observed/memory contact when ammo/cooldown permit; Sim optional target uses
initialTarget/targetId=None, native forward/depth/pitch, JSON activation500.
Existing contacts keep copied XYZ and activation heuristic500/200; no fake point
or hidden lookup. Native sensors only after activation, LOS/range/bounds unchanged.
BT direct audible action allows empty shot; existing tree gates/attack FSM remain.
Human second fire click without selection launches forward; radar point and wire
controls preserved, explicit invalid IDs reject. See TECHNIQUE and targetless tests.
Dimensions/versions/rewards/models unchanged, ammo spam expected, historical scores
noncomparable. Supersedes step3-deferred notes below; reevaluation still deferred.
No live/train/eval/deploy/model overwrite/commit authorization.

Step2 cannon (2026-09-09): shared human/BT/RL Sim.fire_cannon trajectory toward
copied observed/memory/manual point, no target-ID guidance/delayed guaranteed hit.
500 m/s and historical visual parabola/8 m dispersion, first actual collision,
closed exact islands and approximate half-length hull cylinder/4 m vertical.
Movement/diving evade, native friendly fire/posthumous shells, beacons/surface
mines same trajectory; DCA unchanged distinct. CannonFire/Impact/Hit and complete
whitelisted cannon_shell trace; see root tests and TECHNIQUE for limitations.
No observation/action shape/version/reward/model edits; combat semantics shifted,
historical scores noncomparable. Step3/reevaluation deferred. No live server,
training/evaluation/deployment/model overwrite or commit authorized.

Step 1 BT sonar (2026-09-09): shared delayed Sim bot ping only, no timed flag;
5 s wave / 10 s acquired reveal. BT consumes active provider through both deps,
passive 1 Hz, frozen XYZ/time are memory only. Cooldowns BT 10/20/default30 and
RL30 unchanged. test_bt_sonar.py real autodest + existing RL regressions;
schema versions/rewards/models unchanged, historical scores not comparable.
Cannon deferred at step1, implemented by step2 above; targetless torpedo/reevaluation deferred; no live/train/eval/commit.
Human local sonar and global dynamic RNG left unchanged; see TECHNIQUE/followup.

Targeted fairness (2026-09-09): BT waypoint movement now blocks exact island
segments/endpoints and world edges, zero speed without XZ teleport; existing
recovery preserved. Sim bot acoustic/autonomous initial heading is boat-forward,
observed snapshots stay targetId=None, normal guidance/turn radius preserved.
Offset bot 4 m vs human 15 m and launch depth differences deferred; pitch zero
unchanged. Client tx/tz labels are neutral reference points, not acquisition;
no private lock/network additions, preactivation circles unchanged.
Tests: root test_bt_movement.py, rl/test_launch_heading.py, rl/test_bot_fire_los.py,
rl/test_torpedo_guidance.py, tests/test_torpedo_reference.js. Historical outcomes
not directly comparable, schemas/rewards/champions unchanged. Sonar canonical
human-vs-BT and cannon ballistic rules remain unresolved; full fairness unproved.
Read TECHNIQUE.md and AUDIT_FOLLOWUP.md before the RL plan. No live launch,
evaluation, training, deployment, commit or model edit performed/authorized here.

Autogame settling: optional strict bool endCondition.waitForTorpedoes (default
false), enabled true in current root anyBoatSunk v3/v15 scenario, delay 30/600 s
unchanged. Wait for active torpedoes of all natively sunk initial public owners,
including later sinks, with ownerPlayerId/tid identity. Survivors still act;
posthumous kill/draw allowed, timeout overrides pending torpedoes. No pause,
blast/lure/drone wait, observation/reward/model changes. One autogame_settling
trace, final result after settling only. See TECHNIQUE.md; no live launch.

Autogame endings: optional anyBoatSunk/anyTeamEliminated/teamEliminated condition
and monotonic maxDurationSeconds track initial public IDs through native BoatSunk,
never manual deletion or later bots. Batched simultaneous sinks, final trace close,
normal process exit; no RL observations/rewards/model changes. See TECHNIQUE.md
and root test_autogame_end.py (non-listening lifecycle tests only).

Autogame preparation: startDelaySeconds defaults to 0, finite >= 0, no bool;
positive requires boats. Current authorized root scenario: v3/v15, delay 30 s,
unchanged positions, anyBoatSunk and 600 s starting at combat, not spawn.
No Sim.step, BT/RL decisions or beacon detections during preparation; observer
init remains available, mutating intents temporarily refused. No recurrent reset,
observation/reward/model changes or live launch. See root AGENTS and TECHNIQUE.md.

Autogame opt-in (2026-09-09): {"boats": []} remains valid; root autogame.json
is read/validated/preloaded/applied only with --autogame (store_true, default False),
before background tasks/listening. Without the flag, missing/invalid JSON is
ignored, no scenario bots spawn and no autogame trace is emitted. Strict RL
loading and prepared controller reuse remain unchanged. Authorized example:
`./start.sh --trace --autogame --map world`. See TECHNIQUE.md and test_autogame.py;
no live launch, training or model replacement implied.

Approved integrity balance (2026-09-09): destroyer 200, submarine 100, acoustic
lures 10 absolute points from boats/*.json, shared human/BT/RL/headless validation
and per-instance maxIntegrity. Own observations remain current/max with unchanged
32/36/40 shapes; previous reward HP initialized from real instances, same shaping
per absolute point lost. No enemy/lure health observation added. Lures now sustain
3D blast damage; other destructibles deferred. Historical scores no longer directly
comparable, champions unchanged. See root test_integrity.py, tests/test_integrity.js,
TECHNIQUE.md and AUDIT_FOLLOWUP.md; no live/training/deployment authorization.

Server instrumentation (2026-09-09): opt in with `./start.sh --trace --map world`.
Bounded JSONL lives in `logs/game_trace.jsonl`; see `TECHNIQUE.md` and
`rl/AUDIT_FOLLOWUP.md` for coverage and limitations. No new long training run
pending authorized human trace collection and analysis. This instrumentation
does not establish whole-game fairness or browser/network parity and does not
authorize server launch, deployment or champion promotion.

This document defines the architecture, constraints, training pipeline, and evaluation methodology for the AI-controlled opponents used in the game.

Threat ranking followup (2026-09-09): shared Sim/BT and RL ordering is
`(eta <= 0, eta)`, positive geometric ETA first, stable ties; nearby receding
projectiles remain represented for proximity/blast safety. Range, projected
10 s horizon, observation dimensions and action schemas are unchanged, but
historical outcomes are not directly comparable. `--trace` now records each
live RuntimeController observation/action/result and cached public owner/tid,
with decision time, physics step and loaded model fingerprint; no extra sensor
call, private lock, raw BB or recurrent tensors. Automatic stall recovery is
unchanged. See TECHNIQUE.md and AUDIT_FOLLOWUP.md for trace schema and limits.

The goal is to let any coding agent understand the bot system quickly and modify it without breaking gameplay fairness, training validity, or production compatibility.

---

# 1. Purpose

The bots are trained to become strong autonomous opponents in a real-time 3D multiplayer naval combat game.

The game architecture includes:

- an authoritative Python server;
- a Babylon.js 3D client;
- multiplayer networking;
- naval combat simulation;
- AI-controlled ships trained directly against the game environment.

The AI system should produce opponents that are:

- tactically strong;
- robust against different player strategies;
- capable of adapting to complex combat situations;
- fair;
- compatible with the exact same game rules as human players;
- usable in production without requiring a separate simulation implementation.

AI performance must never be achieved by giving bots access to privileged information or by simplifying the game rules for them.

---

# 2. High-Level Architecture

```text
                        GAME
                         │
              ┌──────────┴──────────┐
              │                     │
        Python Server         Babylon.js Client
              │
              │
      Authoritative Simulation
              │
      ┌───────┼────────┐
      │       │        │
   Players   Bots   Game Rules
              │
              │
        Bot Interface
              │
       ┌──────┴──────┐
       │             │
 Observation      Actions
       │             │
       └──────┬──────┘
              │
         AI Policy
              │
      Training Framework
              │
       Self-Play / Evaluation
```

The Python server is the source of truth for gameplay.

Bots interact with the game through a controlled interface that converts game state into observations and bot decisions into valid gameplay actions.

The AI system must not bypass normal game mechanics.

---

# 3. Core Design Principle

The production game and the training environment should share as much simulation code as possible.

Avoid creating a separate "AI version" of the game physics or combat rules.

Whenever possible:

```text
Production simulation
        =
Training simulation
        =
Evaluation simulation
```

Differences should be limited to infrastructure concerns such as:

- rendering disabled during training;
- accelerated simulation;
- deterministic seeds;
- parallel environments;
- logging and instrumentation.

Game mechanics themselves should remain identical.

---

# 4. Authoritative Simulation

The server is authoritative for:

- ship position;
- ship orientation;
- velocity;
- acceleration;
- collisions;
- weapon firing;
- projectile simulation;
- damage;
- destruction;
- cooldowns;
- visibility;
- objectives;
- score;
- victory conditions;
- game state transitions.

Bots must submit actions to the same authoritative simulation.

They must not directly modify:

- position;
- velocity;
- health;
- ammunition;
- cooldowns;
- damage;
- projectile state;
- enemy state.

All consequences must be generated by the normal game simulation.

---

# 5. Bot Interface

The bot layer should expose a clean separation between:

```text
Game State
    ↓
Observation Builder
    ↓
Observation
    ↓
Policy
    ↓
Action
    ↓
Action Validator
    ↓
Authoritative Game Simulation
```

Keep these components isolated.

Recommended responsibilities:

## Observation Builder

Transforms internal game state into information legally available to the bot.

## Policy

Receives observations and produces actions.

The policy may be:

- neural network;
- scripted bot;
- heuristic bot;
- random policy;
- hybrid policy.

The game simulation must not depend on the policy implementation.

## Action Validator

Ensures AI actions respect the same restrictions as player actions.

Invalid actions must be rejected or clamped consistently.

---

# 6. Observation Space

The exact observation schema may evolve, but every observation must respect the fairness invariants defined below.

Typical categories may include:

## Own Ship

- position;
- orientation;
- linear velocity;
- angular velocity;
- current speed;
- throttle;
- rudder;
- health;
- armor state;
- weapon state;
- ammunition;
- cooldowns;
- selected weapon;
- turret orientations.

## Environment

- map-relative information;
- boundaries;
- obstacles;
- relevant terrain;
- objectives;
- capture zones;
- navigation hazards.

## Detected Opponents

Only information legally available through gameplay systems.

Potential fields:

- relative position;
- relative bearing;
- estimated distance;
- estimated velocity;
- visibility state;
- detected ship class;
- known damage information;
- last known position;
- time since detection.

## Projectiles / Threats

Where legitimate:

- detected incoming projectiles;
- relative trajectory;
- estimated time to impact;
- weapon threats.

## Team Information

If the game mode permits it:

- ally positions;
- ally status;
- shared detections;
- objectives;
- team score.

---

# 7. Observation Invariants

These invariants are critical.

## No Privileged Information

Bots must never receive information unavailable to a legitimate human player through game mechanics.

Examples of forbidden privileged information:

- exact position of an undetected enemy;
- hidden enemy health;
- future projectile trajectories unavailable to players;
- enemy inputs;
- enemy policy state;
- server-only tactical information;
- random generator future state;
- information through walls or fog of war;
- future actions.

If uncertain whether a field is legitimate, assume it is privileged until verified.

## No Accidental Information Leakage

Be careful with:

- entity IDs;
- object ordering;
- array lengths;
- sentinel values;
- hidden flags;
- network metadata;
- timestamps;
- simulation internals.

A supposedly harmless feature may leak hidden information indirectly.

---

# 8. Action Space

Bot actions should map to the same conceptual controls available to human players.

Potential actions include:

- throttle;
- steering / rudder;
- aiming;
- turret rotation;
- weapon selection;
- firing;
- target selection;
- defensive actions;
- tactical abilities;
- interaction with objectives.

Prefer normalized continuous actions where appropriate.

Example:

```text
throttle ∈ [-1, 1]
rudder   ∈ [-1, 1]
aim_x    ∈ [-1, 1]
aim_y    ∈ [-1, 1]
fire     ∈ {0, 1}
```

The exact interface should remain stable whenever possible.

Changes to the action space may invalidate existing trained models.

---

# 9. Action Invariants

Bots must obey normal gameplay constraints.

They must not:

- fire during cooldown;
- fire without ammunition;
- rotate weapons faster than permitted;
- exceed ship acceleration limits;
- exceed steering limits;
- issue impossible movement commands;
- bypass animation or gameplay timing;
- directly select invisible enemies;
- perform actions faster than the intended decision frequency.

The action validator should enforce these constraints independently of the AI policy.

Never assume the model will learn to respect rules automatically.

---

# 10. Decision Frequency

AI decisions should occur at a clearly defined frequency.

Keep distinct concepts separate:

```text
physics tick
network tick
AI decision tick
rendering frame rate
```

AI behavior must not accidentally depend on rendering FPS.

The policy should preferably operate at a fixed decision interval.

Document the actual values here when known:

```text
Server simulation tick:      20 Hz (0.05 s, BOT_TICK_INTERVAL / PHYSICS_DT)
AI decision frequency:       4 Hz (0.25 s, five physics ticks per action)
Network update frequency:    20 Hz normally; 10 Hz above 200 ms median RTT
Training simulation speed:   73-101 vector transitions/s in the aidest_v4 run;
                             hardware and evaluation dependent
```

---

# 11. Training Environment

Training should normally run headless.

Rendering must not be required.

The environment should support:

- deterministic seeds;
- fast reset;
- accelerated simulation;
- parallel instances;
- scripted opponents;
- learned opponents;
- self-play;
- reproducible evaluation.

Avoid adding training-specific shortcuts to gameplay mechanics.

The environment wrapper may accelerate or orchestrate the simulation but should not silently alter its rules.

---

# 12. Training Pipeline

Recommended conceptual pipeline:

```text
Game Environment
      ↓
Parallel Environments
      ↓
Observation Collection
      ↓
Policy Inference
      ↓
Action Execution
      ↓
Reward Computation
      ↓
Trajectory Buffer
      ↓
Optimization
      ↓
Updated Policy
      ↓
Evaluation
      ↓
Checkpoint
```

A typical training cycle is:

1. initialize a training run;
2. load configuration;
3. create parallel game environments;
4. initialize or restore the policy;
5. collect gameplay trajectories;
6. compute rewards;
7. update the model;
8. periodically evaluate against reference opponents;
9. save checkpoints;
10. compare the new policy against historical policies;
11. promote models only if evaluation criteria are met.

---

# 13. Training Configuration

Training configuration must be version-controlled or otherwise reproducible.

Every training run should capture at least:

```text
run_id
git_commit
environment_version
observation_version
action_version
reward_version
algorithm
hyperparameters
random_seed
number_of_environments
training_steps
opponent_distribution
checkpoint_source
```

Never rely only on filenames like:

```text
best_model_new_final_v2.pt
```

Every checkpoint must be traceable back to its configuration.

---

# 14. Reward Design

Reward engineering is one of the most sensitive parts of the system.

A policy will optimize the actual reward function, not the intended behavior.

Any reward modification must therefore be treated as a gameplay-design and scientific change, not merely a code change.

Potential reward categories include:

## Terminal Rewards

- victory;
- defeat;
- survival;
- objective completion.

## Combat Rewards

Potential examples:

- damage dealt;
- damage avoided;
- ship destruction;
- successful hits;
- efficient weapon use.

## Tactical Rewards

Potential examples:

- advantageous positioning;
- objective control;
- maintaining effective range;
- avoiding obvious danger.

Shaping rewards should be used cautiously.

The more shaping is introduced, the greater the risk of reward hacking.

---

# 15. Reward Invariants

Never introduce a reward simply because it makes the training curve increase.

A reward is acceptable only if it encourages behavior aligned with actual gameplay success.

Watch for pathological strategies such as:

- hiding indefinitely;
- farming insignificant damage;
- intentionally extending matches;
- circling objectives without engaging;
- firing useless shots because firing is rewarded;
- exploiting collision mechanics;
- exploiting map boundaries;
- repeatedly triggering reward events;
- sacrificing teammates for individual reward;
- exploiting deterministic opponents.

Whenever reward changes are made, evaluate actual gameplay behavior.

Metrics alone are insufficient.

---

# 16. Reward Hacking Procedure

If an agent discovers an unintended strategy:

Do not immediately patch the policy.

First determine whether the behavior reveals:

1. a reward design flaw;
2. a game mechanics exploit;
3. an observation leakage;
4. an evaluation weakness;
5. an opponent-distribution weakness.

Document the discovered exploit.

If the behavior is valid and strategically interesting, consider preserving it.

If it violates intended gameplay, correct the underlying system rather than adding arbitrary penalties whenever possible.

---

# 17. Self-Play

Self-play is expected to be an important component of producing strong opponents.

Avoid training exclusively against the latest policy.

This can create:

- cycles;
- catastrophic forgetting;
- over-specialization;
- unstable strategy distributions.

Prefer an opponent pool.

Conceptually:

```text
Current Policy
     │
     ├── vs current policy
     ├── vs recent checkpoints
     ├── vs historical strong policies
     ├── vs scripted bots
     └── vs reference policies
```

The exact distribution should be configurable.

Example:

```text
40% current/recent policies
30% historical policies
20% scripted reference bots
10% targeted exploit opponents
```

These numbers are illustrative only.

---

# 18. Opponent Pool

Keep a persistent population of useful opponents.

Potential categories:

- latest policy;
- historical best policies;
- aggressive policies;
- defensive policies;
- long-range specialists;
- close-range specialists;
- scripted baseline bots;
- known exploit strategies;
- unusual but valid strategies.

Do not delete old policies solely because they are weaker in aggregate.

A weaker policy may expose a blind spot in a newer agent.

---

# 19. Curriculum Learning

If curriculum learning is used, difficulty should increase gradually.

Potential dimensions:

- number of opponents;
- opponent strength;
- map complexity;
- weapon variety;
- partial observability;
- environmental hazards;
- team size;
- objective complexity.

Avoid a curriculum that produces bots strong only under the curriculum distribution.

Always perform evaluation on the full production distribution.

---

# 20. Checkpoints

Save checkpoints periodically.

A checkpoint should include or reference:

- model weights;
- optimizer state;
- normalization statistics;
- observation schema version;
- action schema version;
- reward version;
- algorithm configuration;
- training step;
- source git commit.

Do not assume old checkpoints remain compatible after observation or action changes.

Explicitly version compatibility.

---

# 21. Model Promotion

Never promote a new model to "best" solely because training reward increased.

Promotion should require evaluation.

A candidate should ideally demonstrate:

- statistically meaningful performance improvement;
- no catastrophic regression against older strategies;
- stable gameplay;
- absence of obvious exploits;
- acceptable behavioral diversity;
- acceptable computational cost.

Production deployment should be a separate decision from training success.

---

# 22. Evaluation Architecture

Evaluation must be isolated from training.

Evaluation episodes must not update:

- network weights;
- optimizer state;
- normalization statistics, unless explicitly designed;
- opponent pools;
- training buffers.

Evaluation should use deterministic or recorded configurations where appropriate.

---

# 23. Primary Evaluation Metrics

## Win Rate

Track win rate against:

- baseline scripted bots;
- previous best model;
- historical checkpoints;
- recent policies;
- specialized opponents.

Never report only one aggregate win rate.

## Elo or Similar Rating

Maintain a rating system across policy versions where practical.

Ratings should be based on a sufficiently connected match graph.

Do not treat Elo as absolute ground truth if matchmaking distributions change.

## Head-to-Head Performance

For candidate model `B` replacing model `A`:

```text
B vs A
A vs B
```

Run enough games to reduce noise.

Where relevant, swap:

- spawn positions;
- teams;
- map sides;
- starting conditions.

---

# 24. Secondary Evaluation Metrics

Track gameplay quality in addition to wins.

Potential metrics:

## Combat

- damage dealt;
- damage received;
- damage differential;
- hit rate;
- shots fired;
- weapon efficiency;
- kills;
- deaths;
- time to first engagement.

## Survival

- average survival time;
- health remaining;
- avoidable damage;
- collision count.

## Positioning

- distance to enemies;
- distance to objectives;
- time spent in advantageous ranges;
- map-control statistics.

## Tactical Behavior

- engagement rate;
- retreat frequency;
- target switches;
- focus-fire behavior;
- flanking behavior;
- objective participation.

## Efficiency

- damage per shot;
- damage per unit time;
- useful action rate;
- wasted weapon usage.

---

# 25. Behavioral Diversity

A strong bot should not necessarily play every game identically.

Monitor behavioral diversity.

Possible indicators:

- action entropy;
- route diversity;
- weapon selection distribution;
- engagement-distance distribution;
- target-selection distribution;
- opening-strategy distribution;
- positional heatmaps.

Loss of diversity may indicate:

- policy collapse;
- overfitting;
- overly deterministic self-play;
- reward shaping problems.

---

# 26. Robustness Evaluation

Evaluate bots under conditions outside the exact training distribution.

Examples:

- unfamiliar opponents;
- older policies;
- scripted edge-case bots;
- different maps;
- unusual weapon combinations;
- different spawn positions;
- different team compositions;
- slight simulation perturbations.

The objective is not merely peak performance but robustness.

---

# 27. Regression Suite

Maintain a fixed evaluation suite.

Every major candidate model should be evaluated against the same reference set.

Example:

```text
evaluation_suite/
├── baseline_aggressive
├── baseline_defensive
├── baseline_random
├── historical_best_001
├── historical_best_002
├── long_range_specialist
├── close_range_specialist
└── known_exploit_policy
```

The suite should evolve carefully.

Do not remove difficult opponents merely because the current model performs poorly against them.

---

# 28. Statistical Discipline

Training results are noisy.

Never draw conclusions from a small number of episodes.

For important comparisons:

- use many evaluation matches;
- report sample size;
- report confidence intervals where practical;
- use multiple random seeds;
- compare distributions, not just averages.

A 52% win rate over 50 games may be meaningless.

A 52% win rate over several thousand balanced games may be meaningful.

---

# 29. Human Evaluation

Automated metrics are necessary but insufficient.

Periodically inspect actual matches.

Look for:

- unrealistic behavior;
- passive strategies;
- exploitative behavior;
- repetitive strategies;
- accidental omniscience;
- unnatural reaction times;
- obviously mechanical aiming;
- tactical mistakes hidden by aggregate metrics.

Human playtesting should be part of the promotion process for important models.

---

# 30. Fairness Invariants

These rules must never be violated.

## Information Fairness

Bots only observe information legitimately available through the game.

## Physics Fairness

Bots use the exact same movement, collision, weapon, and damage systems.

## Timing Fairness

Bots do not act at unrealistic frequencies unless the game design explicitly permits it.

## Weapon Fairness

Bots obey:

- cooldowns;
- aiming limits;
- ammunition limits;
- reload times;
- turret speeds.

## Server Authority

Bots never bypass the authoritative server.

## No Hidden Assistance

Do not silently increase:

- bot damage;
- bot health;
- bot accuracy;
- detection distance;
- projectile speed;
- movement performance.

Difficulty should preferably come from better decisions rather than hidden stat bonuses.

---

# 31. Determinism and Reproducibility

Whenever possible, support deterministic reproduction of problematic matches.

Record:

```text
random_seed
map
spawn configuration
policy versions
game configuration
environment version
```

For important failures, retain enough information to replay the episode.

Reproducibility is especially important for:

- reward exploits;
- NaNs;
- simulation bugs;
- strange policy behavior;
- catastrophic regressions.

---

# 32. Logging

Training logs should separate:

```text
training metrics
evaluation metrics
gameplay metrics
system-performance metrics
```

Important system metrics may include:

- simulation steps per second;
- policy inference latency;
- CPU usage;
- GPU usage;
- environment reset time;
- memory consumption;
- number of parallel environments.

Performance regressions in the environment can significantly increase training cost.

---

# 33. Debugging Procedure

When AI performance degrades, do not assume the neural network is the cause.

Investigate in this order:

1. simulation changes;
2. observation changes;
3. observation normalization;
4. action mapping;
5. reward changes;
6. termination conditions;
7. opponent distribution;
8. training configuration;
9. optimization instability;
10. model architecture.

Many apparent RL failures are environment bugs.

---

# 34. NaN / Numerical Stability

Any NaN or infinity observed in:

- observations;
- rewards;
- actions;
- losses;
- gradients;
- normalization statistics;

must be treated as a critical bug.

Do not silently clamp unexplained NaNs and continue training.

Determine the source first.

---

# 35. Performance

Training infrastructure should prioritize simulation throughput without compromising correctness.

Safe optimizations include:

- headless execution;
- disabling rendering;
- batching inference;
- parallel environments;
- vectorized observation processing;
- efficient serialization;
- avoiding unnecessary allocations.

Unsafe optimizations include:

- changing physics resolution only for training;
- skipping game logic;
- changing collision behavior;
- approximating combat mechanics in ways that alter strategy.

Correctness comes before training speed.

---

# 36. Versioning

Maintain explicit versions for:

```text
environment_version
observation_version
action_version
reward_version
model_version
evaluation_suite_version
```

Any incompatible change must increment the corresponding version.

Do not load an old policy with an incompatible observation or action format without an explicit conversion layer.

---

# 37. Changes That Require Special Attention

Treat the following changes as high-risk:

- observation-space modifications;
- action-space modifications;
- reward changes;
- physics changes;
- weapon balance changes;
- visibility changes;
- game tick changes;
- AI decision-frequency changes;
- episode termination changes;
- self-play opponent-distribution changes;
- normalization changes.

Before implementing such changes, reason about their effect on:

- existing checkpoints;
- training stability;
- evaluation comparability;
- production behavior.

---

# 38. Rules for Coding Agents

When working on the AI system:

1. Read this document before modifying AI-related code.
2. Inspect the relevant implementation before proposing architectural changes.
3. Do not invent undocumented behavior.
4. Preserve server authority.
5. Preserve observation fairness.
6. Preserve training/production simulation equivalence.
7. Do not modify reward semantics casually.
8. Do not change observation or action formats without considering checkpoint compatibility.
9. Add tests for important transformations.
10. Prefer fixing root causes over adding patches around learned behavior.
11. Verify claims using training metrics and actual code.
12. Explicitly identify uncertainty instead of assuming missing details.

---

# 39. Before Changing Reward Logic

Any coding agent modifying rewards should answer:

```text
What exact behavior is this reward intended to encourage?

Can the agent maximize it without actually playing better?

Can the reward be triggered repeatedly?

Could it encourage passive behavior?

Could it conflict with winning?

Could it exploit a game mechanic?

Does it leak information?

How will we measure whether the change helped?
```

If these questions cannot be answered, do not modify the reward yet.

---

# 40. Before Changing Observations

Any observation change should answer:

```text
Is this information available to a human player?

Does it leak hidden state indirectly?

Does it preserve rotational / positional invariance where desired?

Does the scale require normalization?

Does the change break existing checkpoints?

Could the policy infer information from ordering or entity count?
```

---

# 41. Before Promoting a Model

A candidate model should not be promoted without checking:

```text
[ ] Win rate against previous best
[ ] Win rate against historical pool
[ ] Win rate against scripted baselines
[ ] No major regression against specialized strategies
[ ] No obvious reward exploit
[ ] No privileged-information exploit
[ ] Stable gameplay
[ ] Acceptable behavioral diversity
[ ] Acceptable inference latency
[ ] Human match inspection completed
```

---

# 42. Current Project Details

All paths are relative to the repository root. Run Python modules from that
root so imports of `simulation.py`, `geometry.py`, and `bot_ai.py` resolve.

```text
Training algorithm:          RecurrentPPO with MlpLstmPolicy
ML framework:                SB3-Contrib 2.8.0, Stable-Baselines3 2.8.0,
                             Gymnasium 1.2.3, PyTorch 2.11.0
Main AI directory:           rl/
Environment implementation: rl/rl_env.py::SubmarineDuelEnv
Headless simulation adapter: rl/headless.py::HeadlessRunner
Observation builder:         rl/rl_control.py::build_observation
Action interface:            rl/rl_control.py::apply_action
Reward implementation:       rl/rl_env.py::SubmarineDuelEnv.step
Training entry point:        python -m rl.train_ai
Evaluation entry point:      python -m rl.evaluate_ai
Checkpoint directory:        rl/models_rl/<run_name>/
Training configurations:     rl/configs/*.json
Archived configurations:     rl/configs/archive/aisub_v4-v12.json;
                             retained for analysis, not accepted by current loader
Tests:                       python -m unittest -v rl.test_rl_pipeline
Training guide:              rl/TRAINING_RL.md
Metrics / logging:           TensorBoard, VecMonitor monitor.csv,
                             evaluation/match_scores.jsonl,
                             best/selection.json, effective_config.json
Self-play:                   rl/train_ai.py::LeagueSnapshotCallback
Opponent pools:              frozen policy directories loaded by rl/rl_env.py;
                             LRU model cache plus league snapshots
Parallel environments:       8 in the current v15 and v4 configurations
Server simulation tick:      20 Hz
AI decision frequency:       4 Hz
```

Production champions:

- submarine: `rl/models_rl/aisub_v15_scripted/best/best_model.zip`, selected
  checkpoint 500k, SHA-256
  `2849f0c79a15fced51a249720bd25bd4210ee1bafc4c71f79aa942dfaab421c5`;
- destroyer: `rl/models_rl/aidest_v3_scripted/best/best_model.zip`, selected
  checkpoint 3.6M, SHA-256
  `103481713271ed04cf03007f1468898e6b4c928214c12f28ecd90fabfc5066c2`;
- `static/game.js` buttons use `config/conffile.json` keys `bot_rl_sub` and
  `bot_rl_destroyer` via the filtered `init.botRlModels` bootstrap; defaults are
  `aisub_v15_scripted` and `aidest_v3_scripted`, with optional `run:checkpoint`.
  `update_server.sh` synchronizes all model ZIP versions, not just champions.

Current corrected-rule reevaluation (2026-09-09):

- Approved confirmation 94000-94099 is now complete: only v3 and v4 best 300k,
  two CPU single-thread jobs, 400 validated matches, exit zero, empty stderr.
  Fresh scores v3 55.25%, v4 58.00%; paired gain +2.75 pp, seed-clustered
  95% CI [-3.073, 8.573]. This fresh result alone does not establish a gain.
  Combined 92000/93000/94000 scores: 54.416667% vs 59.916667%, +5.50 pp
  [2.016, 8.984], 600 match pairs but 300 distinct seeds, fixed 50/50 opponents.
  Cross-opponent covariance is retained by averaging differences within seed;
  the original analyzer's independent-stratum CIs are archived for comparison.
  This is post hoc confirmation, not a new statistical gate or automatic promotion.
  All 40 launch input hashes unchanged; new artifacts in
  `fairness_corrected/confirmation_94000/`, no completed jobs to relaunch.
   57 regression tests plus 3 local covariance checks pass. Human inspection not
   done; production CPU host/access is not established. The subsequently approved
   LOCAL friatech benchmark is complete, NOT established representative of production:
   i9-12900F, Python 3.12.3, Torch 2.11.0, intra/inter-op=1/1, 100 warmup and
   1000 predictions/model. v3 p50/p95/p99/max/mean ms:
   0.442635/0.460407/0.482280/0.553090/0.443825 (2253.14 predictions/s);
   v4 best 300k: 0.440122/0.461595/0.484843/0.509959/0.442058 (2262.15/s).
   `rl/benchmark_inference.py` uses actual load_model/RuntimeController.model.predict,
   recurrent state carry/reset and real headless observations prepared outside timing.
   New ignored archive: `rl/models_rl/aidest_v4_scripted/evaluation/latency_friatech/20260909_threads1/results.json`.
   Excludes simulation/network/multi-bot load; not the full 250 ms decision budget.
   No production thread defaults changed, no champion promotion or server launch.
   Parent/user handles local server start and human inspection, still missing.
   Next: inspect gameplay and identify/measure the production target, not another run.
- Six CPU single-thread jobs completed for v3, v4 300k and v4 2M, seed series
  92000/93000, 100 episodes per opponent (autosub and frozen submarine v15),
  testCombats and explicit aidest_v4 rewards: 1200 validated matches.
- Corrected scores: v3 54.000%, v4 300k 60.875%, v4 2M 45.250%; paired changes
  relative to v3: +6.875 pp (95% CI 2.447 to 11.303), -8.750 pp
  (-13.708 to -3.792), analytical SE with fixed opponent/seed-stratum weights.
  Read `rl/FAIRNESS_EVALUATION.md` for W/L/D and the completed confirmation.
  No running jobs to relaunch. Historical scores below use different rules.
- Local artifacts in `rl/models_rl/aidest_v4_scripted/evaluation/fairness_corrected/`
  preserve the dirty-code diff, source/input snapshot and hashes; HEAD alone is
  not the executed revision. All 38 input hashes unchanged after completion,
  all six exit codes zero; 57 regression/analysis tests pass. No promotion.

Latest training outcome (historical, before fairness corrections):

- `aidest_v4_scripted` completed 2,007,040 steps from the v3 champion;
- its internal callback retained checkpoint 300k at 50% weighted match score;
- independent testing used seeds 60000 and 70000, 100 episodes per seed and
  opponent for both v4 and the v3 baseline;
- v4 scored 57.50% against `autosub` and 31.75% against submarine v15;
- v3 scored 56.75% against `autosub` and 32.50% against submarine v15;
- both aggregate to 44.625%, so v4 was not promoted.

---

# 43. Current Observation Schema

Every observation is a `numpy.float32` vector in `[-1, 1]`. Positive-only
ratios use `[0, 1]`; absent contacts and threats are zero. Enemy state comes
only from passive or active sonar. The last detected contact is remembered for
30 seconds, but firing requires contact data at most one second old. Eight
relative obstacle/boundary rays cover 0, 45, ..., 315 degrees up to 1,000 m.

Island LOS filters perception, not point-launch permission. BT/legacy/RL weapon
selection uses copied observed XYZ and timestamps, not hidden live player objects.
RL point shots remain limited to the existing one-second fire window; remembering
a contact never counts as a fresh detection. Snapshot torpedoes carry no target-ID
priority or live-position event fallback and must acquire through normal sensors.
Cannon has only delayed target-ID damage, no point-impact path: untracked memory
or a currently island-hidden target is rejected without effects, not auto-hit.

`sub_duel_v1`, shape `(32,)`:

```text
0:10   own movement, depth, integrity, ammunition, cooldowns, emitted noise
10:17  detected/remembered contact, boat-relative position, range, age, depth, noise
17:24  first radar-eligible threat by geometric ETA, position, ETA, 0, 0, range
24:32  eight normalized obstacle/boundary rays
```

`destroyer_duel_v2`, shape `(40,)`:

```text
0:14   own movement, integrity, noise, weapon/lure ammunition and cooldowns, sonar
14:18  surface/bottom/suspended mine ammunition and mine cooldown
18:25  detected/remembered contact fields
25:32  first radar-eligible torpedo threat fields (lock and kind always zero)
32:40  eight normalized obstacle/boundary rays
```

`destroyer_duel_v1`, shape `(36,)`, remains loadable only for historical
checkpoints. It is v2 without the four mine fields: contact `14:21`, threat
`21:28`, rays `28:36`.

Torpedoes use the user-approved strict normal radar contract: local horizontal
range (`boat.radarRangeMeters`, default 30000 m, inclusive), local island LOS and
no crossed thermocline, before threat inference/selection. The shared RL helper
uses exact closed-segment island LOS, mirrored by the client; the former
floor/ceil sampling workaround is removed.
It retains Sim's non-lock planar CPA <= 200 m / 10 s horizon and stable minimum
ETA selection, but never reads acquisition state or type. Own torpedoes remain
excluded. Exact lock and type slots stay zero, including for allied torpedoes.
Shapes/versions still load old checkpoints, but this semantic shift requires
later reevaluation of both candidates and references; old scores are historical.

---

# 44. Current Action Schema

Actions are Gymnasium `MultiDiscrete` integer vectors. `apply_action` validates
shape and bounds, then calls normal `simulation.Sim` methods; cooldown,
ammunition, visibility, depth, and weapon constraints remain authoritative.

```text
sub_duel_v1: MultiDiscrete([5, 5, 5, 3, 2])
  [rudder, throttle, depth, weapon, lure]
  rudder:  -1.0, -0.5, 0.0, 0.5, 1.0
  throttle: -0.35, 0.0, 0.35, 0.65, 1.0
  depth:    1%, 8%, 25%, 45%, 70% of maximum depth
  weapon:   none, acoustic torpedo, autonomous torpedo
  lure:     no, yes

destroyer_duel_v2: MultiDiscrete([5, 5, 5, 2, 2, 4])
  [rudder, throttle, weapon, lure, active_sonar, mine]
  weapon: none, acoustic torpedo, autonomous torpedo, cannon, grenade
  mine:   none, surface, bottom, suspended

destroyer_duel_v1: MultiDiscrete([5, 5, 5, 2, 2])
  historical compatibility; same as v2 without the mine action
```

---

# 45. Current Reward Function

Reward is applied once per 4 Hz decision and configured per experiment. Current
v15/v4 values are:

```text
+10.000  win, once at terminal victory
-10.000  loss, once at terminal defeat
 +0.020  per opponent integrity point lost
 -0.020  per agent integrity point lost
 -0.001  every decision
 -0.020  successful weapon firing
 -0.005  invalid weapon request
 -0.010  successful lure drop
 -0.002  invalid lure request
 -0.010  active sonar ping (destroyer v4)
 -0.002  invalid sonar request (destroyer v4)
 -0.080  successful mine placement (destroyer v4; environment default -0.050)
 -0.005  invalid mine request
 +0.010  transition to a fresh detected contact
```

The small action penalties discourage spam; they are not rewards for firing.
Known risk: invalid-action penalties may still be too small, because some
destroyer checkpoints request invalid weapons very frequently. Draws receive no
terminal reward; model selection separately scores them as half a win.

---

# 46. Current Evaluation Gates

A production candidate currently requires:

```text
Sample size:              two fixed seed series, 100-200 episodes per opponent,
                          for both candidate and current champion
Primary score:            wins + 0.5 * draws, weighted by opponent distribution
Improvement threshold:    at least +3 percentage points aggregated
Regression threshold:     no historical/reference opponent worse by >5 points
Reference suite:          scripted BT baselines plus current frozen RL champion
Inference latency:        must fit the 250 ms production decision budget;
                          no tighter measured threshold exists yet
Human validation:         manual laptop/desktop match inspection is required;
                          no fixed match count exists yet
```

Do not invent a post-hoc gate after seeing results. Confirmation 94000 is
complete, but production latency remains unmeasured and human review not done.
These are explicit evaluation gaps, not permission to assume they passed.

---

# 47. Known Failure Modes

Acoustic/autonomous torpedoes now drop lock on failed real sensor acquisition,
hold current heading/depth (pitch zero), and retain local island avoidance even
without a contact. Neither last acquired nor launch coordinates drive active-phase
homing after failure; pre-activation point guidance and manual wire controls stay
unchanged. Anti-torpedo scan AND previous-lock tracking require exact island LOS.
Autonomous thermocline penetration is sampled once per entity per acquisition
pass, shared across priority/tracking/scan, with fresh retries each eligible tick
(normally 20 Hz). Cumulative detection remains frequency-dependent; no arbitrary
timer or boat-sonar timing contract is added. State emission never resolves live
targetId positions, but retains static remembered coordinates in the existing
payload, which does not distinguish memory from current lock.
`rl/test_torpedo_guidance.py` covers real Sim/headless guidance and acquisition.
This is not whole-game fairness, network parity or guaranteed island pathfinding;
candidate/reference reevaluation and human review remain necessary, not performed.

Audit follow-up: read `rl/AUDIT_FOLLOWUP.md` before launching another run.
RNG isolation and resumed-buffer GAE synchronization are now implemented;
`--report --config` evaluation records per-episode results and artifact hashes.
Fairness is NOT established merely by sharing Sim: active sonar now follows the
approved local-human timing below, not full network/BT parity. Hidden torpedo
visibility now has strict-radar regression tests instead of diagnostic expectations.
The RL destroyer cannon target-depth discrepancy is corrected for v1/v2:
reject `y < -boat.get("flotation", 2) / UNIT_METERS_BOT - 0.05`, matching
`server.fire_cannon_intent`; equality is allowed (2.5 m for flotation 2 m).
The former 4.5 m acceptance is now a Sim/headless regression, including boundary,
shallow/deep targets and no ammo, cooldown or delayed damage on rejection.
Observation/action shapes and existing checkpoints remain compatible, but outcome
metrics before/after this correction are not directly comparable; reevaluate both
candidates and references under the corrected rules. Historical scores above
predate this correction. Sonar, torpedoes, reward and champions are unchanged.

The earlier `(ownerPlayerId, tid)` lock correction is superseded by neutral lock
and type slots under strict radar (section 43). The tooltip hides enemy type;
server acquisition dispatchers are disabled. Sim/headless regressions cover all
three schemas, hidden-candidate invariance, range boundaries, exact thin-island LOS, duplicate
tids and lock-independent inclusion/ordering/ETA. The strict radar/CPA helper is
now shared by Sim and BT; BT combat no longer bypasses visibility via private lock
metadata. Activity checks share radar/LOS/thermoclines with an additional 5 km cap.
Instantaneous Sim position/speed and the historical planar projection remain
approximations: browser interpolation, radar velocity estimation and full network
parity are not tested. See `rl/AUDIT_FOLLOWUP.md` before further fairness work.

RL destroyer active sonar (v1/v2) uses `Sim.bot_sonar_ping(..., timed=True)`;
the default synchronous BT contract remains unchanged. One existing-format
SonarPinged event at emission, no target lookup until shared `Sim.step` ticks.
Canonical own-local human ping: fixed emission origin/cone, expanding front over
5 s, strict expiry at elapsed >= 5 before acquisition. Current wide sonar is
8000 m / 30 degrees: stationary 1 km and 4 km targets become eligible at 0.625 s
and 2.5 s, rounded to the first simulation tick; exact maximum range is excluded.
Check current target position, cone/range, LOS and thermoclines at acquisition;
roll penetration once per ping/target when crossed, not per tick. No speed/noise
detection chance. Reveal-range check uses the current local emitter, no allies;
LOS uses the shared exact island predicate, mirrored by the client.

Acquisition retains its 10 s reveal deadline without per-tick extension,
even after leaving cone/range/LOS. Sim freezes the last observed XYZ and timestamp
behind islands and returns it as untracked memory; RL does not refresh contact age
from this memory. Reappearance in LOS within the deadline permits current tracking
without extending the timer. Observations select the nearest passive/active
contact. Expiry stops tracking and sonar-based firing immediately; the last
observed position remains memory for 30 s. A new ping cannot supply a same-action
shot, but a preexisting legitimate contact can. RL cooldown stays 30 s, including
the existing no-penalty wait behavior; reward coefficients and all shapes/versions
are unchanged. Sim.reset clears pending waves and reveals, shared by training/live.
Tests in rl/test_active_sonar.py exercise real Sim, Headless, RuntimeController,
contact reward/counting and reset. Received/allied ping units and emitter depth
transport are corrected, with client source contracts and optional Node tests in
test_live_contacts.py. Human ID fire now checks exact local island LOS before live
XYZ resolution or effects; manual/remembered point launches remain legal. This is
not full authoritative sonar legality. Browser interpolation/network latency,
complete human contact validation, hidden network payloads and broader BT fairness
remain open; see rl/AUDIT_FOLLOWUP.md for AST handler test limitations.
Old checkpoints still load but require candidate AND reference reevaluation;
historical scores do not establish performance under these timing semantics.

- Long draws dominate some scripted-baseline series: v3 recorded 163 draws in
  200 games against `autosub`; status: open evaluation-sensitivity issue.
- `aidest_v4` peaked at 300k and then regressed to 31.67% internal match score at
  2M; suspected optimization drift/catastrophic forgetting; status: not promoted.
- Destroyer policies can issue many invalid weapon requests despite penalties;
  suspected weak penalty or insufficient action masking; status: open.
- Destroyer performance against submarine v15 remains weak at roughly 32%
  match score; status: open targeted-training problem.
- Observation/action changes invalidate checkpoints. `destroyer_duel_v1` is
  retained for loading old models, while new destroyer training uses v2.

Do not erase historical failure modes after fixing them; retain them as
regression targets.

---

# 48. Current Global Evaluation Brief

The next Astra review is an analysis task, not an automatic promotion or a new
long training run. It should inspect code, configurations, effective run
configs, `monitor.csv`, TensorBoard events, `evaluation/match_scores.jsonl`,
selection metadata, and independent reports under
`rl/models_rl/aidest_v4_scripted/evaluation/`.

Required output:

1. assess simulation equivalence, observation fairness, action validity, reward
   hacking risks, recurrent-state handling, opponent sampling, and checkpoint
   selection;
2. evaluate training stability and explain the v4 early peak and later decline;
3. assess whether the current evaluation suite and sample sizes support the
   promotion decisions;
4. compare the strengths and weaknesses of the production submarine v15,
   destroyer v3, and rejected destroyer v4;
5. identify missing metrics or reproducibility data;
6. propose a prioritized, minimal next experiment with explicit hypotheses,
   success gates, compute budget, and rollback criteria.

Do not modify or overwrite champion checkpoints during the review. Do not
promote v4: its independent aggregate score tied v3 and failed the +3 point
gate.

---

# 49. Final Principle

The objective is not merely to maximize training reward.

The objective is to create opponents that are:

```text
strong
+ fair
+ robust
+ strategically interesting
+ technically reproducible
+ compatible with the real game
```

Whenever those goals conflict, investigate the underlying cause before optimizing the training score.

---

# 50. Key Files

- Training entry point and callbacks: `rl/train_ai.py`
- Gymnasium environment and reward function: `rl/rl_env.py`
- Observation builder and action mapping: `rl/rl_control.py`
- Headless simulation adapter: `rl/headless.py`
- Production policy loader: `rl/rl_runtime.py`
- Independent evaluation: `rl/evaluate_ai.py`
- RL pipeline tests: `rl/test_rl_pipeline.py`
- Active configurations: `rl/configs/`
- Historical configurations: `rl/configs/archive/`
- Local checkpoints and metrics: `rl/models_rl/`
- Training and operations guide: `rl/TRAINING_RL.md`
