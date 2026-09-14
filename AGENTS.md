
# Delegation
- Work directly by default.
- Do not spawn subagents/workers for tasks you can reasonably perform yourself.
- Do not delegate a sequential task merely to wait for the worker's result.
- Delegate only when there is meaningful parallelism or a clear quality benefit.
- Use the minimum number of workers necessary.
- Default worker count: 0.

# Doc
 Do not update documentation, only when i ask to do so

# Efficiency guidelines

Latest mobility runtime v17 is FINAL, OFFICIAL and READ-ONLY as of2026-09-14.
Public aliases are aisub_mobility_runtime_v17/aidest_mobility_runtime_v17;
isolated code and manifests live under rl/bot_versions/v17, with physical
best-model copies. Both deterministic20-route validations reach100% arrival/
open/obstacle,0 sunk/stuck and no weapon/lure/sonar requests. Submarine passes
every gate. Destroyer has one accepted residual failure:1/20 coastal graze,
3.65/200HP, while all other gates pass. Final/intermediate radii are500m; long
routes prefer safe axis-aligned points, then shortest safe near-axis candidates,
then segmented Dijkstra fallback, with every exposed segment<=7.5km. Movement
training and runtime iteration are closed: do not modify/retrain/replace/promote
v17 code, manifests or weights. V16 remains unchanged/read-only. Next planned
phase is combat v18, not prepared or launched. See rl/TRAINING_RL.md. Supersedes
every older mobility ACTIVE/next-step status.

Latest mobility runtime v8 pilots ACTIVE at2026-09-12 15:58+02: simultaneous
fresh CUDA100k destroyer PID533844 seed77542 and submarine PID533854 seed78542.
Both verified8192 rollout steps at429/424FPS. Straightness now uses only segments
with positive actual speed: norm of cumulative forward displacement divided by
forward path length; no forward segment yields0. Reverse remains separate and
cannot produce straightness1. Other v7 rewards/interfaces/architecture/gates
unchanged. Config SHAsdc67bd8c.../ba1a58f8....41 targeted tests/JSON/compile/
diff-check pass. Do not duplicate/kill/extend; no auto promotion/continuation/
live/deploy/commit. See rl/TRAINING_RL.md.

Latest mobility runtime v7 pilots COMPLETE: simultaneous fresh runs finished
106496 steps, no process. Distance reward now applies only at positive actual
speed; beyond100m reverse penalty increases-0.03->-0.05/m. Destroyer selected
100k:100% completion,0 coastal/sunk/stuck,straightness1.0,speed0.346,reverse
99.909%,requests0. Submarine selected25k:100% completion,1% coastal,0 sunk/stuck,
straightness1.0,speed0.347,reverse100%,requests0. Both fail speed/reverse; no
best/promotion/continuation/live/deploy/commit. Candidate SHAs4a536f3b.../
afc90b2a..., finals75d2a080.../aa1aff3c.... Prior40 targeted tests pass. See
rl/TRAINING_RL.md.

Latest mobility runtime v6 pilots COMPLETE: simultaneous fresh runs finished
106496 steps in16m34/9m47, exit0/no process. Completion gates are replaced by
sunk_count<=0 and stuck_count<=2; straightness gate50%. Destroyer selected100k:
100% completion/open/obstacle,1% coastal,0 sunk/stuck,0.415% stationary,
straightness0.963 but speed0.346 and reverse100%; fails speed/reverse, candidate
SHA226c57cc..., final28e45ae8.... Submarine selected25k and remains identical at
all evaluations:0 completion/sunk,100 stuck/stationary,speed/straightness0,
weapon/lure/sonar0; fails speed/straightness/stuck/stationary, candidate
SHA6508d2cb..., finald2d71718.... No best/promotion/continuation/live/deploy/
commit.39 targeted tests/JSON/compile/diff-check pass. See rl/TRAINING_RL.md.

Latest mobility runtime v5 pilots COMPLETE: simultaneous fresh runs finished
106496 steps in18m22/18m28, exit0/no process. Destroyer selected75k:71%
completion,42% obstacle,37% coastal,29% stuck,5.642% stationary,speed0.596,
straightness1.0,lure27.233%; fails completion/obstacle/speed/coastal/stuck/
stationary/lure, candidate SHAdae7ff45..., final4ccb5a44.... Submarine selected
50k:99% completion,98% obstacle,1% coastal/stuck,0.562% stationary,speed0.971,
straightness0.087,weapon/lure/sonar0; fails only straightness, candidate
SHAc7e439a1..., final6dc51508.... No best/promotion/continuation/live/deploy/
commit. Prior319 full/16 mobility tests pass; archives and diff-check clean. See
rl/TRAINING_RL.md. Preserves completed v4/v3/v2 results.

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
clean. See rl/TRAINING_RL.md. Preserves completed v3/v2 results.

Latest mobility runtime v3 pilots COMPLETE: fresh separate runs finished106496
steps in19m44 destroyer/19m27 submarine, exit0/no process. Destroyer selected100k:
98% completion,96% obstacle,2% coastal,2% stuck,speed0.961,straightness0.173,
weapon0 but lure requests100%; candidate SHA7866069d..., final206624cb....
Submarine selected25k:100% completion,0 coastal/stuck,speed0.639,straightness0.092,
weapon/lure/sonar0; candidate SHA9bc636c1.... Its100k improves straightness0.328
but has99% completion,1% coastal/stuck,speed0.638; final SHAb00fd1b1.... All gates
fail; no best/promotion/continuation/live/deploy/commit. Prior61 targeted and14
final mobility tests pass; diff-check clean. See rl/TRAINING_RL.md. Supersedes
its ACTIVE state, not v2 or navigation.

Latest mobility runtime v2 pilots COMPLETE: fresh separate destroyer/submarine
runs finished106496 steps in19m34/17m10, exit0/no process. The -0.1 no-target
penalty eliminates weapon requests in both held-out100 evaluations. Destroyer:
100% completion,0 coastal/stuck/stationary0.415%, speed0.637, straightness0.084,
but lure requests100%. Submarine:99% completion,2% coastal,1% stuck,stationary
0.714%, speed0.967, straightness0.100, lure requests100%. Both fail straightness/
lure gates; destroyer also speed, submarine also zero-coastal. No best/promotion/
continuation/live/deploy/commit. Finals SHAs e2609d1b.../93584800..., selected100k
candidates distinct. Prior315 full and38 targeted tests pass; diff-check clean.
See rl/TRAINING_RL.md. Supersedes its prior ACTIVE state, not v3 or navigation.

Latest goal-oriented shield diagnostic COMPLETE: on the same50 routes, choosing
the safe action with best projected waypoint progress still gives zero coastal
but regresses versus closest-safe: destroyer94% arrival,4% stuck,2% timeout,
1.256% interventions; submarine92% arrival,8% stuck,0 timeout,2.431%
interventions. Reports SHAsa7fa133d.../f5d5c9db.... No adaptation/training/best/
promotion; optional default-off shield restored to the better closest-safe
variant SHA2e17c9c5.... Prior302 full tests and2 post-restore targeted tests pass;
diff-check clean, no process. Supersedes only the proposed next step below.

Latest lookahead/shield navigation diagnostics COMPLETE: optional navigation_v3
keeps13 obs/actions2 but previews the next waypoint at hull-specific150/100m;
progress mode is explicit. Same-route50 control/v3 is behaviorally unchanged:
destroyer96% arrival,6% coastal,2% stuck/timeout; submarine96% arrival,10%
coastal,4% stuck,0 timeout. No lookahead training. Optional navigation-only
predictive shield50m/5s, disabled by default, evaluates all25 actions and chooses
the closest safe command. It reaches zero coastal in both50-route banks, but
destroyer becomes96% arrival/0 stuck/4% timeout and submarine94% arrival/6%
stuck/0 timeout. Adaptation gate fails; no training/best/promotion/live/deploy/
commit. Reports archived under lookahead_diag_*/shield_diag_*; closest shield
SHAsce1f9119.../5c42bf79....302 tests pass in156.185s, diff-check clean, no
process. See rl/NAVIGATION_CURRICULUM.md. Supersedes the next-step status below.

Latest aligned-navigation experiment COMPLETE: separate destroyer/submarine75k
plans finished81920 whole-rollout steps in1h00m48/53m59; no process. Progress,
initial shortest path and efficiency now use the same50m-clearance route as
guidance while geometric route acceptance, obs13/actions2, rewards and gates stay
unchanged. Both selected25k. Destroyer:91% arrival,6% coastal,4% stuck,5% timeout,
0.884% stationary,9.580% near coast,1.070 efficiency, quality0.7521. Submarine:
98% arrival,2% coastal,2% stuck,0 timeout,0.417% stationary,12.018% near coast,
0.991 efficiency, quality0.9396. Candidate SHAsb3c0be56.../627b147a.... All
gates fail: destroyer regresses; submarine fails only zero-coastal. Fresh100
submarine seed552542 confirms98% arrival,3% coastal,2% stuck,0 timeout,0.413%
stationary,13.908% near coast and1.032 efficiency; only zero-coastal fails.
Report SHA5db07271.... No best, continuation, multi-island, live, deploy or
commit.299 tests pass in146.065s and diff-check is clean. See
rl/NAVIGATION_CURRICULUM.md. Supersedes ACTIVE below.

Latest clearance100 navigation experiment COMPLETE: separate destroyer/submarine
safe50-candidate warm-starts finished106496 steps in1h26m31/1h23m15; no process.
Only guidance_clearance_m changed50->100. Selected internal candidate destroyer
at75k:96% arrival,9% coastal,4% stuck,0 timeout,0.971% stationary,7.845% near
coast,1.086 efficiency, quality0.8204; submarine at50k:97% arrival,6% coastal,
3% stuck,0 timeout,0.601% stationary,6.284% near coast,1.049 efficiency,
quality0.8745. Candidate SHAs2a251964.../b0f66ba3.... All gates fail and the
margin does not improve the safe50 result; no best/fresh100/final500/multi-island/
continuation/live/deploy/commit. Three targeted tests/prior298 full pass and
diff-check clean. See rl/NAVIGATION_CURRICULUM.md. Supersedes ACTIVE below.

Latest safe-corridor navigation pilots COMPLETE: navigation_v2 now keeps the
graph waypoint until the direct goal segment has generic50m clearance from
islands/world bounds. Separate hull warm-start100k runs evaluate/save candidates
every25k; candidate/ is independent from gate-protected best/. Internal100
candidate destroyer:97% arrival,5% coastal,3% stuck,0 timeout,0.793% stationary,
8.188% near coast,1.067 efficiency; submarine98% arrival,3% coastal,2% stuck,
0 timeout,0.424% stationary,10.392% near coast,1.017 efficiency. Fresh100
destroyer seed502542:97% arrival,4% coastal,2% stuck,1% timeout,0.470% stationary,
1.089 efficiency; submarine seed512542:97% arrival,3% coastal,3% stuck,0 timeout,
0.638% stationary,1.003 efficiency. All gates fail; no best/final500/multi-island/
continuation/live/deploy/commit. Candidate SHAs4fd1040e.../2447a9a0.... Submarine
completed106496 steps in51m11; destroyer checkpoint100k is complete but its
wrapper timed out during final evaluation, which was recovered independently.
No process remains;298 tests pass and diff-check is clean. See
rl/NAVIGATION_CURRICULUM.md. Supersedes the next-experiment state below.

Latest waypoint navigation pilot/continuation COMPLETE: navigation_v2 keeps13
obs/2 movement actions but substitutes the next safe graph waypoint while the
goal is occluded. Separate hull warm-start pilots then separate100k continuations,
all106496-step runs. First held-out100 destroyer:100% arrival,3% coastal,0 stuck/
timeout/stationary,1.101 efficiency; submarine97% arrival,8% coastal,3% stuck,
0 timeout,0.593% stationary,1.062 efficiency. Fresh continuation routes regress:
destroyer97% arrival,6% coastal,0 stuck,3% timeout,0.188% stationary,1.092;
submarine92% arrival,17% coastal,4% stuck/timeout,0.830% stationary,1.201.
Continuation durations18m57/20m06; checkpoint SHAs8ea038d7.../db0c7ec2...,
finals distinct. All gates fail; no best/final500/multi-island/continuation/live/
deploy/commit, no process.295 tests pass. See rl/NAVIGATION_CURRICULUM.md.
Supersedes the next-experiment choice in the one-island status below.

Latest one-island navigation phases COMPLETE: separate destroyer/submarine safe
continuations,106496 steps each in16m42/15m45, no process. Easy routes are
600-1200m, exactly one blocker, graph detour<=1.3,240s. Optional anticipatory
coastal proximity reward defaults0; latest uses-0.1 under hull-specific150/100m
margins and reports near-coast fraction. Final held-out100 destroyer:21% arrival,
28% coastal episodes,15% stuck,64% timeout,1.751% stationary,31.559% near coast,
1.140 successful efficiency. Submarine:88% arrival,21% coastal,8% stuck,4%
timeout,1.599% stationary,21.750% near coast,1.101 efficiency. All promotion
gates fail; no best, multi-island, continuation, live, deploy or commit. Last
checkpoint SHAs e7851ee9.../b1ba326f..., final distinct. A150m destroyer margin
regressed; next experiment needs one explicit structural avoidance/representation
choice. Single-island rejection cap is20000 and200 eval seeds regress. See
rl/NAVIGATION_CURRICULUM.md;293 tests pass. Supersedes older navigation statuses
below.

Optimize for compute and usage efficiency.

## Delegation
- Work directly by default.
- Do not spawn subagents/workers for tasks you can reasonably perform yourself.
- Do not delegate a sequential task merely to wait for the worker's result.
- Delegate only when there is meaningful parallelism or a clear quality benefit.
- Use the minimum number of workers necessary.
- Default worker count: 0, but subgent/worker can be used to launch RL training at least

## Verification
- Match testing effort to the size and risk of the change.
- Do not add or run broad test suites for trivial, reversible changes.
- Run the smallest relevant verification first.
- If relevant checks pass, do not repeatedly rerun them without a reason.

# Repository Guidelines

Latest navigation pilot100k COMPLETE: fresh destroyer alone on world, seed11542,
navigation_v1 obs13/action rudder+throttle, no opponent/weapons.106496 steps in
19m08 including100 held-out routes, exit0/no process. Results:5% arrival,44%
coastal damage episodes,9.248 mean coastHP,37% stuck,58% timeout,3.976%
stationary,1.245 path efficiency on successes. Arrival/coast/stuck gates fail;
no best selected. Checkpoint SHA6a134069..., final distinct. Native30m coastal
danger now damages bots/humans equally at1HP/s.287 tests before launch, inputs
unchanged. No auto continuation/live/promotion/deploy/commit/subagent. See
rl/NAVIGATION_CURRICULUM.md. Supersedes the PREPARED navigation status below.

Latest open-navigation pilot COMPLETE: fresh seed12542,106496 steps/8m17 incl
100 held-out routes, exit0/no process.15% arrival,0 coastal damage,4% stuck,81%
timeout,1.463% stationary,1.159 successful efficiency. Arrival98%/stuck2% gates
fail; no best and one-island stage remains blocked. Checkpoint SHA3039de40...,
final distinct.289 tests before launch; no continuation/live/deploy/commit/subagent.

Latest behavior pilots COMPLETE: v16/v16b acquisition warm-start v15, same
seed9542/protocol, penalty-0.1/-0.5; each106496 steps/11m00 and10m57, exit0/no
process. Same-situation deterministic180 v15/v16/v16b: score33.542/33.958/
32.083%, unacquired shots28.081/25.028/15.759%, misaligned89.067/93.321/90.381%,
invalid requests93.143/94.684/93.839%. Behavior gates fail both, no best,
promotion or continuation. v8 mobility prepared but NOT launched.278 full tests
plus config smokes pass. No live/deploy/commit/subagent. See rl/BEHAVIOR_PILOTS.md.
Supersedes only the next-behavior-experiment status.

Latest V7 FINAL COMPLETE and independently compared: phase5 ended2026-09-10
22:15:46+02,106496 new steps/15m14,no process. Internal det34.167%,sampled
76.944%. Independent320 duels seeds200000-19,autosub/sub15: phase4/phase5
settled det42.5/32.5%,sampled75.833/76.667%. Phase5-phase4 det -10
[-15.507,-4.493]pp and sampled +0.833[-4.318,5.985]pp,normal95% CI/20 clusters.
Phase5 significantly harms deterministic runtime without established sampled
gain.8 jobs exit0,124 hashes/job,320 traces,zero mines/caps. Recommended but NOT
promoted: phase4 checkpoint100k SHA9a513b31..., still0W/6L/34D settled on final
det batch. Planned V7 training complete; no continuation/live/promotion/deploy/
commit/subagent. See rl/V7_DEFENSE_PILOT.md. Supersedes phase5 ACTIVE below.

Latest authorized V7 phase5 FINAL ACTIVE:2026-09-10 22:00:12+02 PID304338,
aidest_v7_defense_continue4_seed8542_final100k, CUDA workers304358-304365.
Warm-start phase4 checkpoint100k SHA9a513b31..., optimizer loaded, seed8542.
Final planned phase100k ends at106496 new whole-rollout steps. Schedule-preserving
entropy0.000975 to0.0003, completed curriculum disabled. Verified24576/548FPS
finite optimizer;298 archived inputs/196ZIP unchanged after startup before docs,
15 targeted/prior275 full tests and prior320 independent duels. Log
/tmp/virtualWorld_aidest_v7_defense_continue4_seed8542_final100k.log. Do not
duplicate/kill or auto-extend after completion. No independent reevaluation/live/
promotion/deploy/commit/subagent. Supersedes phase4 COMPLETE-only block below,
preserving its comparison; see rl/V7_DEFENSE_PILOT.md.

Latest V7 phase4 COMPLETE and independently compared:106496 new steps/14m29,
ended2026-09-10 21:40:29+02, no process. Internal det41.667%,sampled79.722%.
Independent320 duels seeds190000-19, autosub/sub15: phase3/phase4 settled det
36.25/45%, sampled74.167/70.417%. Paired phase4 gains +8.75[3.388,14.112]pp
det and -3.75[-8.843,1.343]pp sampled, normal95% CI/20 clusters. Deterministic
gain supported; sampled decrease not established. Zero mines/caps.8 jobs exit0,
121 unchanged hashes/job,320 traces validated. No auto continuation/live/
promotion/deploy/commit/subagent. See rl/V7_DEFENSE_PILOT.md. Supersedes phase4
ACTIVE below; final planned100k is defensible but requires explicit authorization.

Latest authorized V7 phase4 ACTIVE:2026-09-10 21:25:41+02 PID300707,
aidest_v7_defense_continue3_seed7542_review100k, CUDA workers300727-300734.
Warm-start phase3 checkpoint100k SHA3a0438b..., optimizer loaded, seed7542.
Remaining phase plans200k but --stop-after-steps100000 reviews at106496 new
whole-rollout steps. Schedule-preserving entropy0.00165 toward0.0003 over200k,
completed curriculum disabled. Verified24576steps/558FPS finite optimizer;293
archived inputs/192ZIP unchanged after startup before docs,15 targeted/prior275
full tests and prior320 independent duels. Log /tmp/virtualWorld_aidest_v7_defense_continue3_seed7542_review100k.log.
Do not duplicate/kill or auto-continue after review. No independent reevaluation/
live/promotion/deploy/commit/subagent. Supersedes phase3 COMPLETE-only status
below while preserving its comparison; see rl/V7_DEFENSE_PILOT.md.

Latest V7 phase3 COMPLETE and independently compared:106496 new steps/16m41,
ended2026-09-10 21:06:11+02, no process. Internal det34.167%,sampled73.056%.
Independent320 duels seeds180000-19, autosub/sub15, det40 and sampled120 per
checkpoint: phase2/phase3 settled det27.5/35%, sampled72.5/78.333%. Paired
phase3 gains +7.5[0.302,14.698]pp det and +5.833[0.016,11.650]pp sampled,
normal95% CI/20 seed clusters; sampled lower bound is near zero. Invalid weapon
attempts93.817->33.05/duel, no mines/caps.8 CPU jobs exit0,118 unchanged hashes/
job,320 traces validated. Phase3 det has0 wins, so no promotion. No automatic
continuation/live/deploy/commit/subagent. See rl/V7_DEFENSE_PILOT.md. Supersedes
phase3 ACTIVE block below; another100k review is defensible but needs a choice.

Latest authorized V7 phase3 ACTIVE:2026-09-10 20:49:11+02 PID296452,
aidest_v7_defense_continue2_seed6542_review100k, CUDA workers296472-296479.
Warm-start phase2 checkpoint100k SHAf3148eab..., optimizer loaded, seed6542.
Remaining phase plans300k but --stop-after-steps100000 reviews at106496 new
whole-rollout steps. Schedule-preserving config starts entropy0.002325 toward
0.0003 over300k and disables completed curriculum. Verified16384steps/575FPS
finite optimizer;288 archived inputs/188ZIP unchanged after startup before docs,
15 targeted/prior275 full tests. Log /tmp/virtualWorld_aidest_v7_defense_continue2_seed6542_review100k.log.
Do not duplicate/kill or auto-continue after review. No independent eval/live/
promotion/deploy/commit/subagent. Phase2 completed106496/15m20: deterministic
33.333%(0W/20L/40D), sampled81.389%(130W/17L/33D),16721 invalid weapons/no mines.
See rl/V7_DEFENSE_PILOT.md. Supersedes phase2 ACTIVE block below.

Latest authorized V7 phase2 ACTIVE:2026-09-10 20:28:54+02 PID294428,
aidest_v7_defense_continue_seed5542_review100k, CUDA workers294449-294456.
Warm-start from immutable first-pilot checkpoint100k SHA41c5fa5d..., optimizer
loaded, new seed5542. New phase plans400k but --stop-after-steps100000 reviews at
106496 new whole-rollout steps; --resume intentionally resets phase curriculum/
entropy schedules. Verified24576 steps/559 cumulative FPS and finite optimizer.
283 archived inputs including184 ZIPs unchanged after startup before docs;15
targeted tests, prior275 full. Log /tmp/virtualWorld_aidest_v7_defense_continue_seed5542_review100k.log.
Do not duplicate/kill or automatically continue after review. No independent
eval/live/promotion/deployment/commit/subagent. Supersedes COMPLETE-only status
below while preserving first-pilot findings; see rl/V7_DEFENSE_PILOT.md.

Latest V7 defense pilot COMPLETE:106496 fresh steps in16m14, ended2026-09-10
20:16:10+02; no process remains. Internal100k selection deterministic35%
(1W/19L/40D,60) vs sampled75%(108W/18L/54D,180), autosub80/frozen sub15 70%
sampled. No mines, but sampled has29373 invalid weapon attempts; deterministic
only11 launches/no lures, so immature and not promotable.100k checkpoint and
both best archives have identical weight payload; final106496 is distinct and
unevaluated.273 inputs excluding4 post-start status docs plus all180 prior ZIPs
unchanged after completion. No continuation/independent comparison/live/
promotion/deployment/commit/subagent. See rl/V7_DEFENSE_PILOT.md. Supersedes
the ACTIVE V7 block below; a next phase requires an explicit choice.

Latest authorized V7 defense pilot ACTIVE:2026-09-10 19:59:34+02 PID291249,
aidest_v7_defense_seed4542_review100k, fresh model/no resume, CUDA workers
291267-291274. Config plans500k but --stop-after-steps100000 reviews at106496
whole-rollout steps; seed4542, v3 obs101/action5 no mines, dual eval at100k.
Verified16384steps/492 cumulative FPS and finite first optimizer.277 archived
inputs including180 prior ZIPs unchanged after startup before docs;275 full+7
final v3 targeted tests. Log /tmp/virtualWorld_aidest_v7_defense_seed4542_review100k.log.
Do not duplicate/kill healthy job or automatically continue after review. No
live/promotion/deployment/commit/subagent. Supersedes PREPARED-only status below.

Latest RL design decision PREPARED, NOT TRAINED: destroyer_duel_v3 has101 obs,
six radar-visible torpedo slots (relative position/velocity,CPA/ETA,threat rank)
and six lure slots (relative position,lifetime,ownership). Foreign lures and all
enemy torpedoes obey range/LOS/thermocline; no private lock/type/target. RL mine
action and mine state are removed (5 action components); human/BT/v1/v2 gameplay
unchanged. Old checkpoints remain loadable but cannot warm-start v3. New config
rl/configs/aidest_v7_defense.json: fresh seed4542,500k planned,dual eval100k;
mine reward-1 is unreachable defense-in-depth. No training/live/promotion/
deployment/commit.275 full tests then7 final v3 targeted tests pass. See
rl/TRAINING_RL.md and test_destroyer_v3_observation.py.
Supersedes the next-experiment-undecided portion below, not completed V6 results.

Latest V6 continuation COMPLETE:507904 new steps, ended2026-09-10 14:52:31+02,
1h21m43; no training process remains. Independent comparison400 duels seeds
170000-19, autosub/sub15, deterministic references/current and3 action seeds for
sampled source/current. Settled v4/v5/source-v6-sampled/continue-det/
continue-sampled=66.25/80/81.25/48.75/70.833%. Continue sampled-source sampled
-10.417[-16.560,-4.274]pp,20 seed clusters; self-mine HP3084.078 vs851.900.
All10 jobs exit0,107/108 inputs unchanged/job, no600s cap. Artifacts valid;
final507904 distinct and unselected. No automatic remaining1.5M continuation,
promotion/runtime/deployment/commit. A new experiment requires explicit decision
and one isolated dimension. See rl/V6_PILOT_COMPARISON.md and rl/TRAINING_RL.md.
Supersedes the ACTIVE continuation block below. No subagent used.

Latest authorized V6 continuation ACTIVE:2026-09-10 13:30:32+02:00 PID262667,
aidest_v6_continue_seed3542_review500k from untouched pilot checkpoint500k.
Planned2M new steps, CLI --stop-after-steps500000 pauses for review at507904
whole-rollout steps. Seed3542 CUDA8workers262687-262694; verified24576steps,
421FPS finite optimizer. LR5e-5, entropy0.0003 constant, curriculum completed0;
rules/rewards/architecture unchanged, dual eval every100k.13 targeted tests,
270 archived inputs/model hashes unchanged after startup before docs. No subagent.
Log /tmp/virtualWorld_aidest_v6_continue_seed3542_review500k.log; see
rl/TRAINING_RL.md. Do not duplicate/kill healthy job or automatically continue
after review boundary. No promotion/deployment/commit. Supersedes older no-launch
notes only for this explicitly authorized phase.

Dual RL evaluation protocol prepared, no new training: optional
sampled_action_seed_offsets adds independent deterministic best/ and sampled/best
selection. New rl/configs/aidest_v6_dual_eval.json retains pilot500k settings;
old configs/models/runtime unchanged.267 tests pass. See rl/TRAINING_RL.md
for240 matches/eval budget and firstdeath300s limitation. No launch/promotion.

Latest v6 references comparison COMPLETE:200 duels160000-19 with v4/v5
deterministic and v6-500k sampled3 policy seeds per situation. Settled scores
81.25/82.5/81.25%;20 seed-clustered CIs v6-v4 0[-9.627,9.627]pp and
v6-v5 -1.25[-9.817,7.317]. No equivalence/promotion.5exit0,102/103 unchanged
hashes/job,262tests. No new training or gameplay/runtime changes; read
rl/V6_PILOT_COMPARISON.md for complete protocol and limitations.

Latest V6 mine ablation complete:80 duels150000-19,500k deterministic control
vs no-agent-mines diagnostic. First5/40%,settled2.5/40%;32 self-attributed
first sinks in control,5860.019 self-mineHP. No self-mine damage under ablation,
but mostly draws. Two jobs exit0,103 input hashes unchanged/job,261tests pass.
No gameplay/reward/runtime/model changes or further training. See
rl/V6_PILOT_COMPARISON.md; supersedes prior proposed-only ablation status.

## Latest V6 Diagnostic Status

Pilot complete at507904 steps. Fresh comparison140000 complete:160 duels,
v6BEST100k/checkpoint500k x deterministic/sampled x autosub/sub15 x20 seeds.
First scores51.25/10/81.25/76.25%; settled53.75/6.25/77.5/77.5%.
Late deterministic32/40 self-attributed first sinks,5886.111 self-mine HP.
Four jobs exit0,102/103 hashes unchanged/job;259 tests pass. No training active
or new continuation authorized here. Diagnostic sampling only, no gameplay,
reward, standard inference or weights changes. See rl/V6_PILOT_COMPARISON.md.
Supersedes older V6 ACTIVE notes. No promotion/deployment/commit performed.

## Latest RL Status (2026-09-10)

V6 fresh pilot ACTIVE at2026-09-10T09:09:31+02:00, launched09:08:39, PID244030,
aidest_v6_scripted_seed2542_pilot500k, CUDA RTX5080, workers244048-244055.
Actual provenance new_model/source null/resume null/seed2542; total_steps500000,
v5 config otherwise unchanged except identity/description.258 current tests pass.
First8192 rollout then16384 steps/470 cumulative FPS, optimizer8 updates and
finite logged metrics verified. Next eval100k/checkpoint250k.99 input hashes
and58 model hashes unchanged after launch; read-only archive under
rl/models_rl/launch_manifests/aidest_v6_scripted_seed2542_pilot500k/.
Externally restored admin access resolved prior blocker without policy edits.
Curriculum100k/entropy500k compress with duration, not isolated causal proof.
Do not duplicate or kill healthy pilot; see rl/TRAINING_RL.md for evidence/log.
Overrides historical no-training instructions ONLY for this authorized pilot;
no automatic3-5M continuation before pilot evaluation/report, no live/promotion/
deployment/commit/old model overwrite. Existing v5 diagnostic work preserved.

Latest diagnostic80 COMPLETE on explicit authorization: v4best300k/v5best2M
x autosub/sub15 x20 fresh seeds130000-130019,2 CPU single-thread jobs exit0.
First scores80/78.75%,settled80/77.5%; v5-v4 -1.25[-12.755,10.255] then
-2.5[-13.685,8.685]pp,paired95% normal CI20 seed clusters/40 pairs, covariance
retained.47 continuations,no600s cap;2W->D and1L->D(v5 posthumous grenades).
379/638 torpedoes,79.68/82.60% blind,0.586/0.582 enemy hull HP/launch;
grenades91.78/86.18% offensive hull damage.99 hashes unchanged/job,
81 source/JSON+18ZIP,9 docs additionally archived;102101 decisions checked,
256 tests pass. New diagnostic80_130000 archive under v5 evaluation.
See rl/DUEL_DIAGNOSTICS.md. Supersedes proposed-not-run80 notes below, not
independent1200 results; no pooling/causal/equivalence claim. No next long
training justified. Proposed ONLY: frozen-v5 diagnostic blind-shot ablation,
one variable/fresh seeds/separate authorization; NOT run. No gameplay/reward/
config/weights edits,live,promotion,deployment,commit or campaign process left.

V5 training COMPLETE: final artifact 2026-09-10T03:11:25+02:00, 2007040
new steps; selected BEST at2000000/internal score0.7916666667, SHA256
1af86f9b3f1be7235be4a8994ebbfd8e538d0935c078358dfd1ea8374fe8e9de.
Best and policy_final are distinct (final also has one additional optimizer
rollout); no training process remains. Supersedes historical ACTIVE/not-launched
notes below, which describe earlier observations, not current instructions.
Independent comparison COMPLETE: six CPU single-thread exit0 jobs,1200 matches,
12 groups100, seeds110000-110099/120000-120099, testCombats, unchanged v5 config
(v4 rewards), autosub/frozen sub15. v3/v4best300k/v5best scores69.5/80.5/80.375%.
V5-v4 -0.125[-3.624,3.374]pp; v5-v3 +10.875[7.036,14.714]pp, paired
seed-clustered95% CIs (200 seeds/400 pairs). Incremental +3pp gate against v4
FAILS; no demonstrated improvement over v4, no equivalence claim or promotion.
123 launch hashes unchanged through evaluation;256 tests pass. New ignored
archive: rl/models_rl/aidest_v5_scripted_seed1542/evaluation/independent_110000_120000/.
Only five status docs changed afterward; gameplay/config/rewards/weights intact.
First death/300s, not autogame settling/600s. V5 torpedoes15.87 vs v4 10.425/duel;
acoustic exhaustion147/400 vs26/400. Next proposed, NOT run:80 instrumented
v4/v5 duels on fresh seeds for damage/rejection/settling diagnosis; no further
training, live server, promotion, deployment, overwrite or commit in this turn.
See rl/FAIRNESS_EVALUATION.md and rl/TRAINING_RL.md for complete evidence.

## Overview

`virtualWorld` is a real-time multiplayer naval/submarine combat game. An authoritative Python server (Flask + Flask-SocketIO over eventlet) arbitrates all gameplay, while a monolithic BabylonJS client (`static/game.js`) renders and sends *intents*. Optional AI bots run as behavior trees or reinforcement-learning agents. Read `TECHNIQUE.md` for the full architecture.

## Project Structure & Module Organization

- `server.py` — entry point: network, tick loop, authoritative arbitration.
- `simulation.py` — pure game logic (`Sim` class, `step(dt)`); no I/O or Flask deps.
- `events.py` — dataclass events dispatched to sockets/logs/replay.
- `geometry.py`, `nav_graph.py` — pure geometry helpers and bot navigation graph.
- `bot_ai.py` — behavior-tree engine; tree definitions live in `bots/ai/*.json`.
- `boats/` — ship specs (`destroyer.json`, `submarine.json`).
- `maps/` — world maps; `config/conffile.json` — port and day length.
- `rl/` — RL package, training configs, tests, documentation and local model artifacts; read `rl/AGENTS.md` before RL work.
- `models/`, `static/textures/` — 3D assets; `templates/` — HTML pages.

## Build, Test, and Development Commands

```bash
python3 -m venv .venv                      # create virtualenv
.venv/bin/pip install -r requirements.txt  # install dependencies
./start.sh                                 # run server (HTTPS, default port 7000)
./stop.sh                                  # stop server
python migrate_nav_graph.py                # one-shot: rebuild nav graphs in maps/
```

## Coding Style & Naming Conventions

- Python: 4-space indentation, `snake_case`, full type hints (`typing`), dataclasses for events.
- Docstrings and inline comments are written in **French** — keep this convention.
- JSON specs use `camelCase` keys (`radarRangeMeters`, `dayDurationSeconds`).
- `server.py` and `static/game.js` are large; make surgical edits and put new game state in `simulation.py` (never I/O-coupled).

## Testing Guidelines

Long training ACTIVE at 2026-09-10T01:10:30+02:00, newest explicit user launch
authorization supersedes historical agent-only no-launch notes. PID210501,
aidest_v5_scripted_seed1542, CUDA RTX5080, eight workers210519-210526;
warm-start untouched v4best300k, seed1542, 2M new steps, config unchanged.
Verified8192 first rollout and24576 steps/523 cumulative FPS after optimizer,
finite logged losses/KL; not completed or evaluated yet. First eval100k,
checkpoint250k, outputs only in new run. Log:
/tmp/virtualWorld_aidest_v5_scripted_seed1542.log. Read-only source archive98
files including untracked Python/configs/maps/boats/BT, git diff/status/revision
and SHA manifests: rl/models_rl/launch_manifests/aidest_v5_scripted_seed1542/.
All98 launch inputs and v3/v4/sub15 hashes verified unchanged before status-doc
updates. Exact command/model SHA/resources/limits in rl/TRAINING_RL.md.
No automatic later monitoring promise; do not duplicate/kill this healthy job.
No commit/deploy/live/promotion/reward edit or existing model overwrite.

Warm-start pipeline prepared (2026-09-10), long run NOT launched here. New
rl/configs/aidest_v5.json preserves v4 except identity and seed1542, 2M new steps.
Parent's later long-run authorization remains; use new aidest_v5_scripted_seed1542
from untouched v4 best300k. CLI rejects nonempty output, validates architecture,
seeds native load before setup, records loaded provenance; --resume is a new
phase, not exact continuation. See rl/TRAINING_RL.md and rl/AGENTS.md. CUDA compute
verified, no throughput claim; no model overwrite/live/deploy/promotion/commit.

Diagnostic80 completed (2026-09-10), newest explicit user authorization supersedes
older no-evaluation/training notes: v3/v4 best300k x autosub/sub15 x20 seeds98000-19.
80 validated duels, two CPU single-thread exit0 jobs,79 input hashes unchanged/job.
First scores67.5/76.25%, settled65/73.75%; four W->D,34 continuations,no600s cap.
V4 fires432 torpedoes pre-end (354blind), grenades supply93.79% enemy hull damage.
No gameplay/reward/default termination/model edits. See rl/DUEL_DIAGNOSTICS.md.
Parent is authorized for later autonomous long training; this diagnostic agent
did not launch it. Recommend sole major dimension warm-start v4best300k, ~2M
new steps/seed1542/new directory, otherwise v4 scripted config unchanged.
No commit/deploy/promotion/model overwrite/live server. Existing dirty work preserved.

STEP4 completed (2026-09-10), explicitly authorized reevaluation after STEP1/2/3:
six CPU single-thread jobs,1200 validated matches,100/opponent/series96000/97000,
testCombats, current aidest_v4 rewards and HP200/100/10, autosub/frozen sub15 best.
All exit0,125 launch hashes unchanged. v3/v4 best300k/v4 2M scores67/75.5/66.5%;
paired seed-clustered gains+8.5[4.727,12.273] and-0.5[-4.481,3.481] pp.
247 Python tests pass; reusable analyzer now retains cross-opponent covariance.
Fresh rules_steps123 archive; see rl/FAIRNESS_EVALUATION for WLD/hashes/resources,
ammo/rejection counts and limits. Evaluation remains first death/300s, not
autogame torpedo settling/600s. Frozen opponent semantics affected too; no old
score pooling/global robustness claim. Supersedes reevaluation-deferred notes
below, not live validation gaps. No gameplay/reward/config/model edits, training
run, promotion, deployment, live server or commit. Proposed next:80 instrumented
v3/v4 duels for ammo/rejection/settling diagnosis, only on separate authorization.

Step3 targetless torpedo (2026-09-09): human and Sim acoustic/autonomous accept
absent target, initialTarget/targetId=None, forward native depth/pitch/offset,
no fake point. Explicit invalid/stale/occluded human IDs reject, never fallback.
Native activation/sensors/LOS/range/bounds unchanged; blind RL uses JSON500,
contact heuristic500/200 unchanged, ammo/cooldown apply. BT direct audible action
can fire empty; existing tree gates and known-target attack FSM stay tactical.
Human first click aims, radar chooses point, second same button fires forward;
wire manual/exclusive unchanged. Tests rl/test_targetless_torpedo.py,
test_server_fire_los.py, tests/test_targetless_torpedo.js. Shapes/rewards/models
unchanged, possible ammo spam expected, historical scores noncomparable.
Supersedes historical step3-deferred notes below; reevaluation remains deferred.
No live/train/eval/deploy/model overwrite/commit authorized.

Step 2 cannon (2026-09-09): shared Sim.fire_cannon point trajectory for human/BT/RL,
no delayed target-ID damage. Observed/memory/manual points copied; continuous shell
curve against tick-sampled current hulls, first closed exact island obstruction.
Historical 500 m/s, visual parabola/8 m dispersion; hull cylinder half existing
lengthMeters (default100 m), vertical4 m, diving below flotation evades. Native
30-point damage/friendly fire, shooter excluded, shells survive shooter sinking.
Active/passive beacons and surface mines use trajectory/native destruction; AA
unchanged distinct. CannonFire shotId + CannonImpact; full whitelist cannon_shell
trace. See TECHNIQUE and test_cannon_ballistics.py/tests/test_cannon_ballistics.js.
No observation shape/reward/model changes; historical scores noncomparable.
Step3/evaluation deferred, no live/train/eval/deploy/model/commit authorization.

Step 1 BT sonar (2026-09-09): bot_sonar_ping always emits and returns [], no
timed flag/synchronous acquisition. Shared RL wave 5 s / acquired reveal 10 s;
BT active contacts refresh through server/headless deps, passive remains 1 Hz.
Frozen XYZ/time behind islands never become fresh detected IDs; no live reload.
BT cooldowns 10/20 s and default 30 unchanged. test_bt_sonar.py uses real autodest;
RL regressions retained. Schema versions unchanged, semantics/scores shifted.
At step1 cannon was deferred; step2 above now implements it. Targetless torpedo and reevaluation deferred;
no server/model/train/eval/commit. Human local sonar/global RNG unchanged.

Targeted fairness (2026-09-09): BT _drive_to_waypoint checks exact geometry LOS,
island endpoint and existing world margin; blocked XZ unchanged, speed zero,
existing waypoint recovery preserved, no new automatic navigation/teleport.
Bot acoustic/autonomous launch starts boat-forward; copied legitimate XYZ,
snapshot targetId=None, normal seeker/turn radius unchanged. Offset remains
bot 4 m vs human 15 m; initial pitch zero and launch depths unchanged/deferred.
Three client labels use Point de reference, never infer acquisition from tx/tz;
no private lock boolean/network change, circles mean activation only.
See test_bt_movement.py, rl/test_launch_heading.py, tests/test_torpedo_reference.js
and TECHNIQUE.md/AUDIT_FOLLOWUP. Historical outcomes not directly comparable;
sonar canonical human-vs-BT and cannon ballistic rules unresolved, full fairness
not proved. No live/eval/train/deploy/commit/model edit authorized by these fixes.

Spectator UX: first init boat is viewed through the existing player/bot-view
render loop and remote mesh, with no local Boat, ownership or controller change.
Existing botsBtn becomes Changer unite; Tab/Shift-Tab cycle every live human/bot
across teams. Default radar uses viewed ship/team sensor rules, not omniscience;
local allmap remains optional diagnostic. Clear contact caches on view changes;
private sensor history/ammo are not forwarded (ammo explicitly unavailable).
Sinking/disconnect follows the next survivor, empty scene auto-follows arrival.
Keep server spectator guards and all previous torpedo/fairness fixes untouched.
See tests/test_spectator.js (full client NullEngine), test_spectator.py,
README and TECHNIQUE; no live launch or browser/mobile parity implied.

Autogame settling: endCondition.waitForTorpedoes is optional strict bool, default
false; current anyBoatSunk scenario enables true, preserving v3/v15 XYZ/caps,
delay 30 and maxDurationSeconds 600. Wait only for authoritative active torpedoes
of ALL natively sunk initial owners, including further sinks during settling.
Public ownerPlayerId/tid pairs distinguish owner-local IDs; survivors keep acting,
posthumous kills/draws count, no blast/lure/drone wait. Timeout bounds settling;
without a timeout no extra watchdog. One optional autogame_settling trace, final
result only after settling/timeout. Example condition:
{"type": "anyBoatSunk", "waitForTorpedoes": true}. Tests remain non-listening.

Autogame preparation: optional startDelaySeconds defaults to 0, finite numeric
>= 0 (bool rejected), positive requires boats. Current authorized local scenario
is v3 destroyer / v15 submarine at existing XYZ/caps, delay 30, anyBoatSunk/600.
Models preload and bots spawn before listening; monotonic preparation then yields
without Sim/BT/RL or either beacon ticker, while observer init stays accessible.
Mutating SocketIO intents temporarily return autogame_preparing; no queued retry.
Initial depth deadline is shifted at start; no global live-clock/multiplier rewrite.
End duration starts on the first ready tick, never during preparation; traces
autogame_ready/autogame_started plus snapshots distinguish the phases. Default
--autogame bypass remains. See TECHNIQUE.md and test_autogame*.py/test_spectator.py.
Next authorized usage: ./start.sh --trace --autogame --map world. This change
does not authorize live launch, deployment, training, model overwrite or commit.

Autogame end conditions: optional endCondition types anyBoatSunk,
anyTeamEliminated, teamEliminated (required existing teamId); independent optional
positive finite maxDurationSeconds, monotonic after combat starts. Initial public IDs only,
native BoatSunk events batched per tick; manual removal/reset is not elimination.
No end fields = no automatic stop; empty boats remains valid without end fields. Final native events,
forced snapshot and autogame_end precede trace close and main-greenlet wakeup for
normal process exit (no socketio.stop or os._exit). See test_autogame_end.py and
TECHNIQUE.md; subprocess lifecycle tests use no listening port. No live launch.

Autogame/self-grenade followup (2026-09-09): {"boats": []} is a valid empty
scenario; only --autogame (store_true, default False) reads/validates/preloads
and applies it. Without the flag, even missing/invalid JSON has no effects and
no scenario boats or autogame trace are produced. Authorized example:
`./start.sh --trace --autogame --map world`.
Validated startup-only scenarios spawn through server.spawn_bot
before background tasks/listening, with explicit teams/XYZ (10 m/u)/radians and
strict RL loading, never silent BT fallback. Human grenade owner immunity removed;
BT/RL remain vulnerable, self damage excluded from GrenadeExploded.dealt.
See TECHNIQUE.md, test_autogame.py and test_integrity.py. No live launch implied.

Approved integrity balance (2026-09-09): destroyer 200, submarine 100,
acoustic lures 10 points in boats/*.json; per-instance maxIntegrity, absolute
damage, percentage HUD/own RL ratios, unchanged observation shapes and per-point
reward coefficients. Persistent 3D lure blast damage; other destructibles deferred.
Historical scores are no longer directly comparable; champions unchanged.
See test_integrity.py, tests/test_integrity.js and TECHNIQUE.md; no live server,
deployment, training or model overwrite implied by these regressions.

Threat ranking followup (2026-09-09): Sim/BT and RL rank positive ETA before
passed zero-ETA CPA candidates, retaining nearby receding proximity risks.
No radar range, 10 s horizon or observation schema change; historical outcomes
are not directly comparable. Opt-in RLDecision traces actual vectors/actions/results
and cached public threat identity, never LSTM/BB or another sensor call.
Automatic stall recovery remains unchanged; see TECHNIQUE.md and rl/AUDIT_FOLLOWUP.md.

Server trace: `./start.sh --trace --map world` opts into `logs/game_trace.jsonl`
(4 Hz snapshots, native gameplay events, 20 MiB plus five backups; OFF by default).
See `game_trace.py`, `test_game_trace.py` and `TECHNIQUE.md`. Do not start a server
or a long training run without authorization; human-session trace collection and
analysis remain pending. Stored server state is not proof of client visibility
or whole-game fairness. Preserve concurrent gameplay corrections.

Run `OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 venv/bin/python -m unittest discover -v` using the existing local venv. Root geometry/Sim and `rl/` regressions include sensor LOS, remembered point launches and torpedo lock loss; they do not establish whole-game fairness or browser/network parity. See `rl/AUDIT_FOLLOWUP.md` for remaining gaps. Manual verification, when authorized: run `./start.sh`, connect the client, and inspect `logs/server.log`. Toggle `debug_log.py` categories at runtime via the in-game `debug <cat>` cheat.

## Commit & Pull Request Guidelines

No Git history is currently present, so conventions are not yet established. Keep commits small and focused, reference the module touched, and update `TECHNIQUE.md` for any gameplay or network-behavior change.

<!-- lean-ctx -->
## lean-ctx

lean-ctx is active — the MCP tools replace native equivalents.
Full rules: LEAN-CTX.md (open on demand — do not auto-load).
<!-- /lean-ctx -->
