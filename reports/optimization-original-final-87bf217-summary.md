# Single-observer original87 final baseline

The new original87 baseline passed all nine primary repeats and all six separately recorded pressure repeats. New-core primary batch/fast reports are pending: the operator paused the sequence during753 pressure before applying a later hotfix. Completed753 container/scale measurements remain753; historical4cfff0a comparisons are not latest results. Every repeat is retained in JSON/CSV, with source hashes and unchanged conditions.

Primary source: `reports/optimization-original-final-87bf217-20261006T145840Z-0d4630.json`; SHA256 `35700d3cfff60022c381f38fab52a3d3daf745b842b1e29309a9cf68a1c5a676`. Elapsed2972.814698s. Each path has three repeats,40 isolated1024-FE probes,30s warmup and120s fixed240-input steady work. All240 inputs per primary sample accepted32000FE:7680000FE.

| Path / repeat | Low full p50 bounds (ms) | p95 bounds (ms) | p99 bounds (ms) | DBtx / account SQL statements per240 inputs | DBtx / statements per input |
| --- | --- | --- | --- | --- | --- |
| same / 1 | 2741.798–2744.428 | 2940.635–2942.988 | 2944.981–2948.061 | 3719 / 36061 | 15.495833 / 150.254167 |
| same / 2 | 2829.939–2831.790 | 2935.373–2937.243 | 3042.385–3044.245 | 3425 / 33489 | 14.270833 / 139.537500 |
| same / 3 | 2827.953–2829.638 | 2952.055–2954.390 | 3028.467–3030.500 | 3440 / 33707 | 14.333333 / 140.445833 |
| cross / 1 | 2755.543–2757.882 | 2864.082–2866.950 | 2974.949–2978.411 | 3475 / 33517 | 14.479167 / 139.654167 |
| cross / 2 | 2831.541–2833.626 | 2941.503–2944.029 | 2951.589–2953.306 | 3433 / 33519 | 14.304167 / 139.662500 |
| cross / 3 | 2827.515–2829.433 | 2941.175–2943.373 | 3033.389–3035.189 | 3466 / 31700 | 14.441667 / 132.083333 |
| mixed / 1 | 1839.333–1841.244 | 3376.799–3381.656 | 3577.268–3579.112 | 3386 / 29601 | 14.108333 / 123.337500 |
| mixed / 2 | 2655.986–2657.686 | 3076.357–3078.321 | 3164.647–3166.435 | 3691 / 32560 | 15.379167 / 135.666667 |
| mixed / 3 | 2165.827–2167.576 | 3359.895–3361.873 | 3770.548–3772.535 | 3750 / 33120 | 15.625000 / 138.000000 |

First/full low-flow percentile bounds happen to match in these saved samples. Bounds include source/target RCON intervals and0.1s target polling. At40 probes nearest-rankp99 is the observed maximum; these are descriptive sample percentiles without a tail guarantee. Aggregates below are medians of the three repeat percentiles, never pooled120-probe quantiles.

| Path | Repeat-median p95 bounds (ms) | Repeat-median DBtx / statements per240 inputs |
| --- | --- | --- |
| same | 2940.635–2942.988 | 3440 / 33707 |
| cross | 2941.175–2943.373 | 3466 / 33517 |
| mixed | 3359.895–3361.873 | 3691 / 32560 |

Main-path counter_end is captured after drive and **before final conservation drain**. Counts assess the same fixed240-input workload window plus real capture boundaries, not a complete drained lifecycle. Some tail work can finish during capture; subsequent drain TX/WAL cost is unmeasured and is not backfilled. Low-flow, warmup and setup/cleanup are separate. Backpressure includes recovery and its drain before counter_end. Full resource conservation cannot establish that full-lifecycle cost was measured.

| Path / repeat | Actual steady receiving endpoints and maximum successful-pull gaps |
| --- | --- |
| same / 1 | same_sink_0(A):7552000 FE, gap≤2.001981s |
| same / 2 | same_sink_0(A):7488000 FE, gap≤3.001678s |
| same / 3 | same_sink_0(A):7488000 FE, gap≤3.002051s |
| cross / 1 | cross_sink_0(B):7520000 FE, gap≤2.504839s |
| cross / 2 | cross_sink_0(B):7488000 FE, gap≤3.002014s |
| cross / 3 | cross_sink_0(B):7584000 FE, gap≤1.000325s |
| mixed / 1 | mixed_sink_0(A):3648000 FE, gap≤3.497725s; mixed_sink_1(B):3904000 FE, gap≤3.500478s |
| mixed / 2 | mixed_sink_0(A):3648000 FE, gap≤2.999909s; mixed_sink_1(B):3968000 FE, gap≤5.002153s |
| mixed / 3 | mixed_sink_0(A):3776000 FE, gap≤4.501817s; mixed_sink_1(B):3808000 FE, gap≤3.501527s |

All primary sinks had actual service, including both mixed receivers in every repeat. Gap includes phase edges and is not a pending-demand latency measurement. Per-repeat low-flow receiver totals, drain tails and exact capture intervals remain in JSON/CSV. The all-phase independent primary ledger was 86,768,640FE accepted and 86,768,640FE extracted; each path's latest cumulative checkpoint matches its ledger. Local FE buffers, SQL pool and allocation remaining were independently empty after drain. Repeated cumulative checkpoints and SQL/WAL copies are never added as assets.

All15 recorded drive/hold windows had observer_saturated=false and late_rounds0;120s drive durations and every maximum lateness/RCON quantile are retained. This establishes delivery under the supplied fixed load, not factory capacity. Native whole-phase MSPT/TPS, baseline WAL writes/bytes/barriers and Sql-helper/batch counters remain UNMEASURED. Both reports record no other live backend sessions; root observation SQL is excluded from the ct_dev account SQL statement events, which count attempts/retries rather than JDBC round trips.

Pressure source: `reports/optimization-original-pressure-87bf217-20261006T144116Z-38d872.json`; SHA256 `2eef02f7cf00467abb7db371e137e8edc814ea900734362692af422a6cfd9f8e`. All six are functionally passed, preserving recovered SQL failures:

| Case / repeat | Source inputs | DBtx / account statements | Deadlock retries / SQL statement errors | Late rounds / observer saturated |
| --- | --- | --- | --- | --- |
| backpressure / 1 | 240 | 3103 / 33677 | 0 / 0 | 0 / False |
| backpressure / 2 | 240 | 3104 / 34011 | 0 / 0 | 0 / False |
| backpressure / 3 | 240 | 3052 / 32778 | 0 / 0 | 0 / False |
| hotspot / 1 | 1680 | 15109 / 167838 | 281 / 281 | 0 / False |
| hotspot / 2 | 1680 | 15219 / 162270 | 191 / 191 | 0 / False |
| hotspot / 3 | 1680 | 15527 / 162676 | 149 / 149 | 0 / False |

Hotspot has240 rounds across seven sources (four hot and three cold):1680 inputs, not240 source events. The281/191/149 hotspot deadlock retries and equal statement-error counts are retained; worker errors/rejections/quarantines are zero. Backpressure holds output for120s, retains the quiet held-state evidence, then observes recovery before the cost counter ends. These cases are separate workloads and are not substituted into the three primary path goals.

Frozen context: `reports/optimization-baseline-context.json` (SHA256 `0d3c0117751db2978461cf833647be190ef328db2122b25403b9c9ab5e7c8856`). Keep30% fewer successful DB transactions **for each same/cross/mixed fixed input window**,40% same-path full-output upper-boundp95 reduction, and cross upper-boundp95 regression≤20%. The default10% descriptive comparison flag is separate. Separate idle30% and integrity/fairness targets remain unchanged and are not fabricated from primary data. No goal assessment is made before complete new-core batch/fast reports.

Runtime identity is supplied by the archived87 launches and operator; saved PIDs/worlds/session/epoch/argv hashes distinguish the new original-final worlds from prior runs. git_head753 is the checkout, not a loaded runtime declaration. The legacy harness lacks class-loader CodeSource and command-specific reply body tags. One business RCON observer ran without sidecars; prefix, fixed-input and conservation checks passed, without proving raw body attribution absent from the old driver.

The initial original physical-container10/120 attempt remains failed and retained separately, with second-probe source32/target0 and no measurable E2E. Its later2/420 success does not erase that failure. This FE baseline does not measure physical chest or world-save timing.

[Full JSON](optimization-original-final-87bf217-summary.json) · [all15 per-repeat rows](optimization-original-final-87bf217-summary.csv)
