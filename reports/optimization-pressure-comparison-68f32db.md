# Original87 /68f32db pressure evidence

Both standalone children exited0 and functionally passed all six windows. Actual source names and SHA256 were read from the exact completed --label entries in the two sequence reports and verified against the raw files. This does not label pending current B/C or the entire parent sequence completed.

| Cohort | Actual raw file | SHA256 | Parent-recorded child UTC start → end | Raw observer elapsed seconds |
| --- | --- | --- | --- | --- |
| original87 | reports/optimization-original-pressure-87bf217-20261006T144116Z-38d872.json | 2eef02f7cf00467abb7db371e137e8edc814ea900734362692af422a6cfd9f8e | 2026-10-06T14:41:16Z → 2026-10-06T14:58:07Z | 1009.918451 |
| current68 | reports/optimization-current-pressure-68f32db-20261006T170630Z-ae7dcd.json | f7b8c245e530d247744dc76c20a336fa364960d2130c30de33b3b88868fd1ef2 | 2026-10-06T17:06:30Z → 2026-10-06T17:22:54Z | 982.619924 |

Conditions match:30s warmup,120s phase,3 repeats,no low-flow probes. Backpressure supplies240×32000FE with120s intentionally disabled external outputs and then recovery. Hotspot supplies240 rounds×7 sources(four hot/three cold),1680×32000FE. Inputs are counted from actual native acceptance events. All12 observer drive/hold windows retain rounds, lateness and saturation; all expected rounds and accepted quantities passed.

| Case /repeat | Actual source events | DBtx original →68 | ct_dev account SQL events original →68 | Completed worker tasks original →68 |
| --- | --- | --- | --- | --- |
| backpressure /1 | 240 | 3103 → 2970 | 33677 → 49154 | 588 → 968 |
| backpressure /2 | 240 | 3104 → 2971 | 34011 → 50042 | 583 → 979 |
| backpressure /3 | 240 | 3052 → 2813 | 32778 → 38720 | 575 → 870 |
| hotspot /1 | 1680 | 15109 → 9274 | 167838 → 155251 | 3939 → 5529 |
| hotspot /2 | 1680 | 15219 → 9583 | 162270 → 158120 | 3967 → 5466 |
| hotspot /3 | 1680 | 15527 → 9401 | 162676 → 153123 | 4038 → 5177 |

| Case /repeat-median metric | Original →68 | Change | Default10% descriptive regression |
| --- | --- | --- | --- |
| backpressure /DBtransactions | 3103.000000 → 2970.000000 | -4.29% | False |
| backpressure /SQL_statement_events | 33677.000000 → 49154.000000 | 45.96% | True |
| backpressure /SQL_statement_timer_wait_sum_seconds | 7.562138 → 14.230393 | 88.18% | True |
| backpressure /worker_tasks_distribution | 583.000000 → 968.000000 | 66.04% | False |
| backpressure /actual_output_FE_per_second | 56804.896917 → 56753.914664 | -0.09% | False |
| backpressure /max_actual_pull_gap_seconds | 122.367015 → 122.369350 | 0.00% | False |
| backpressure /post_counter_drain_seconds | 0.077379 → 0.081980 | 5.95% | False |
| backpressure /recovery_to_verified_drain_seconds | 12.833468 → 12.952679 | 0.93% | False |
| hotspot /DBtransactions | 15219.000000 → 9401.000000 | -38.23% | False |
| hotspot /SQL_statement_events | 162676.000000 → 155251.000000 | -4.56% | False |
| hotspot /SQL_statement_timer_wait_sum_seconds | 45.120183 → 276.186464 | 512.11% | True |
| hotspot /worker_tasks_distribution | 3967.000000 → 5466.000000 | 37.79% | False |
| hotspot /actual_output_FE_per_second | 409332.293411 → 443466.263090 | 8.34% | False |
| hotspot /max_actual_pull_gap_seconds | 6.007117 → 2.003464 | -66.65% | False |
| hotspot /post_counter_drain_seconds | 6.586550 → 0.489495 | -92.57% | False |

These are repeat medians/individual paired observations, not statistical confidence tests. Worker counts describe scheduled work rather than SQL transactions. All raw driver regressions and independently derived flags remain in JSON. The pressure workload cannot substitute for the frozen primary same/cross/mixed30% DB goal.

| Cohort /case /repeat | Deadlock retries | Account SQL errors | Worker errors | Queue rejections | Quarantines |
| --- | --- | --- | --- | --- | --- |
| original87 /backpressure /1 | 0 | 0 | 0 | 0 | 0 |
| original87 /backpressure /2 | 0 | 0 | 0 | 0 | 0 |
| original87 /backpressure /3 | 0 | 0 | 0 | 0 | 0 |
| original87 /hotspot /1 | 281 | 281 | 0 | 0 | 0 |
| original87 /hotspot /2 | 191 | 191 | 0 | 0 | 0 |
| original87 /hotspot /3 | 149 | 149 | 0 | 0 | 0 |
| current68 /backpressure /1 | 0 | 0 | 0 | 0 | 0 |
| current68 /backpressure /2 | 0 | 0 | 0 | 0 | 0 |
| current68 /backpressure /3 | 0 | 0 | 0 | 0 | 0 |
| current68 /hotspot /1 | 0 | 0 | 0 | 0 | 0 |
| current68 /hotspot /2 | 0 | 0 | 0 | 0 | 0 |
| current68 /hotspot /3 | 0 | 0 | 0 | 0 | 0 |

Original hotspot SQL errors/retries281/191/149,total621, remain visible despite recovery and functional success. No recovered error is removed by comparing only completed outputs.

| Cohort /backpressure repeat | Recovery to verified drain(s) | First output raw reply-end delay(ms) | Conservative recovery-entry→successful-pull interval(ms) |
| --- | --- | --- | --- |
| original87 /1 | 12.883601 | 0.585098 | 0.010466–0.585098 |
| original87 /2 | 12.833468 | 0.550136 | 0.006710–0.550136 |
| original87 /3 | 12.727364 | 0.427122 | 0.005409–0.427122 |
| current68 /1 | 12.983552 | 0.825840 | 0.028753–0.825840 |
| current68 /2 | 12.952679 | 0.501813 | 0.006359–0.501813 |
| current68 /3 | 12.316410 | 0.648063 | 0.005628–0.648063 |

First output extracts held credit, not a new source input E2E. The raw delay is a reply-end observation; reconstructed intervals include its command span. Each held pool/local-buffer/allocation-remaining snapshot and the quiet repeat remain in JSON/CSV, separately, without adding mirrors as assets. The~122s maximum successful-pull gap includes the deliberately disabled120s outputs and quiet guard; it does not prove eligible-demand starvation.

All receiver service and waiting observations, including every cold endpoint, follow. First/last times are seconds relative to that sample's phase start. Maximum gap includes phase edges and sampled successful pulls; it is not a per-packet/eligible-demand latency.

| Cohort /case /repeat | Receiver(server) | Actual phase output FE | Successful pulls | First output(s) | Last output(s) | Maximum observed unserved/pull gap(s) |
| --- | --- | --- | --- | --- | --- | --- |
| original87 /backpressure /1 | backpressure_sink_0(A) | 3856000 | 121 | 122.359756 | 134.621134 | 122.359756 |
| original87 /backpressure /1 | backpressure_sink_1(B) | 3824000 | 120 | 122.360241 | 134.520092 | 122.360241 |
| original87 /backpressure /2 | backpressure_sink_0(A) | 3856000 | 121 | 122.366632 | 134.579957 | 122.366632 |
| original87 /backpressure /2 | backpressure_sink_1(B) | 3824000 | 120 | 122.367015 | 134.479044 | 122.367015 |
| original87 /backpressure /3 | backpressure_sink_0(A) | 3856000 | 121 | 122.374633 | 134.615733 | 122.374633 |
| original87 /backpressure /3 | backpressure_sink_1(B) | 3824000 | 120 | 122.374963 | 134.514454 | 122.374963 |
| original87 /hotspot /1 | hot_sink_0(A) | 5248000 | 164 | 3.505413 | 119.506688 | 3.505413 |
| original87 /hotspot /1 | hot_sink_1(B) | 7328000 | 229 | 5.506376 | 119.507375 | 5.506376 |
| original87 /hotspot /1 | hot_sink_2(B) | 6832000 | 214 | 3.006530 | 119.507712 | 3.996706 |
| original87 /hotspot /1 | hot_sink_3(C) | 7008000 | 219 | 2.005466 | 119.506290 | 4.497250 |
| original87 /hotspot /1 | cold0_sink_0(A) | 7456000 | 233 | 3.507232 | 119.508341 | 3.507232 |
| original87 /hotspot /1 | cold1_sink_0(B) | 7488000 | 234 | 3.001698 | 119.508993 | 3.001698 |
| original87 /hotspot /1 | cold2_sink_0(C) | 7456000 | 233 | 3.502637 | 119.502439 | 3.502637 |
| original87 /hotspot /2 | hot_sink_0(A) | 7360000 | 230 | 5.007829 | 119.504041 | 5.007829 |
| original87 /hotspot /2 | hot_sink_1(B) | 5344000 | 167 | 5.008146 | 119.504797 | 5.008146 |
| original87 /hotspot /2 | hot_sink_2(B) | 6592000 | 206 | 3.505256 | 119.505335 | 3.505256 |
| original87 /hotspot /2 | hot_sink_3(C) | 7232000 | 226 | 6.007117 | 119.503529 | 6.007117 |
| original87 /hotspot /2 | cold0_sink_0(A) | 7552000 | 236 | 2.006565 | 119.506464 | 2.006565 |
| original87 /hotspot /2 | cold1_sink_0(B) | 7488000 | 234 | 3.006329 | 119.507405 | 3.006329 |
| original87 /hotspot /2 | cold2_sink_0(C) | 7552000 | 236 | 2.007995 | 119.501595 | 2.007995 |
| original87 /hotspot /3 | hot_sink_0(A) | 5984000 | 187 | 3.504712 | 119.505886 | 4.499793 |
| original87 /hotspot /3 | hot_sink_1(B) | 6704000 | 210 | 5.006252 | 119.506372 | 5.006252 |
| original87 /hotspot /3 | hot_sink_2(B) | 6688000 | 209 | 5.506110 | 119.506708 | 6.502247 |
| original87 /hotspot /3 | hot_sink_3(C) | 7456000 | 233 | 3.004865 | 119.505251 | 3.004865 |
| original87 /hotspot /3 | cold0_sink_0(A) | 7584000 | 237 | 0.501391 | 119.508120 | 1.006710 |
| original87 /hotspot /3 | cold1_sink_0(B) | 7520000 | 235 | 2.503353 | 119.509702 | 2.503353 |
| original87 /hotspot /3 | cold2_sink_0(C) | 7584000 | 237 | 1.003290 | 119.502071 | 1.003290 |
| current68 /backpressure /1 | backpressure_sink_0(A) | 4048000 | 127 | 122.372538 | 135.270915 | 122.372538 |
| current68 /backpressure /1 | backpressure_sink_1(B) | 3632000 | 114 | 122.373517 | 133.946102 | 122.373517 |
| current68 /backpressure /2 | backpressure_sink_0(A) | 4048000 | 127 | 122.368768 | 135.230639 | 122.368768 |
| current68 /backpressure /2 | backpressure_sink_1(B) | 3632000 | 114 | 122.369350 | 133.905773 | 122.369350 |
| current68 /backpressure /3 | backpressure_sink_0(A) | 3824000 | 120 | 122.366076 | 134.498518 | 122.366076 |
| current68 /backpressure /3 | backpressure_sink_1(B) | 3856000 | 121 | 122.366937 | 134.600728 | 122.366937 |
| current68 /hotspot /1 | hot_sink_0(A) | 7648000 | 239 | 0.508944 | 119.505290 | 0.516308 |
| current68 /hotspot /1 | hot_sink_1(B) | 7552000 | 236 | 2.003464 | 119.506046 | 2.003464 |
| current68 /hotspot /1 | hot_sink_2(B) | 7584000 | 237 | 1.005635 | 119.506502 | 1.005635 |
| current68 /hotspot /1 | hot_sink_3(C) | 7552000 | 236 | 1.504272 | 119.504786 | 1.504272 |
| current68 /hotspot /1 | cold0_sink_0(A) | 7648000 | 239 | 0.501810 | 119.507756 | 0.514139 |
| current68 /hotspot /1 | cold1_sink_0(B) | 7616000 | 238 | 0.503123 | 119.508758 | 0.995757 |
| current68 /hotspot /1 | cold2_sink_0(C) | 7616000 | 238 | 0.504775 | 119.502234 | 1.001657 |
| current68 /hotspot /2 | hot_sink_0(A) | 7584000 | 237 | 0.508932 | 119.507229 | 1.494458 |
| current68 /hotspot /2 | hot_sink_1(B) | 7552000 | 236 | 2.005586 | 119.507967 | 2.005586 |
| current68 /hotspot /2 | hot_sink_2(B) | 7616000 | 238 | 1.006308 | 119.508363 | 1.006308 |
| current68 /hotspot /2 | hot_sink_3(C) | 7584000 | 237 | 1.504007 | 119.506481 | 1.504007 |
| current68 /hotspot /2 | cold0_sink_0(A) | 7648000 | 239 | 0.501939 | 119.509057 | 0.524277 |
| current68 /hotspot /2 | cold1_sink_0(B) | 7616000 | 238 | 0.503156 | 119.509802 | 0.994798 |
| current68 /hotspot /2 | cold2_sink_0(C) | 7616000 | 238 | 1.004061 | 119.502738 | 1.004061 |
| current68 /hotspot /3 | hot_sink_0(A) | 7488000 | 234 | 2.002583 | 119.506811 | 2.002583 |
| current68 /hotspot /3 | hot_sink_1(B) | 7520000 | 235 | 1.508832 | 119.507734 | 1.508832 |
| current68 /hotspot /3 | hot_sink_2(B) | 7616000 | 238 | 0.506188 | 119.508182 | 1.002598 |
| current68 /hotspot /3 | hot_sink_3(C) | 7552000 | 236 | 1.008750 | 119.506423 | 1.008750 |
| current68 /hotspot /3 | cold0_sink_0(A) | 7616000 | 238 | 0.501347 | 119.508996 | 0.990039 |
| current68 /hotspot /3 | cold1_sink_0(B) | 7616000 | 238 | 1.002472 | 119.509915 | 1.002472 |
| current68 /hotspot /3 | cold2_sink_0(C) | 7616000 | 238 | 0.503553 | 119.503097 | 0.998198 |

| Cohort /hotspot repeat | FE actually drained after counter_end | Separate final drain(s) |
| --- | --- | --- |
| original87 /1 | 4944000 | 6.586550 |
| original87 /2 | 4640000 | 7.534452 |
| original87 /3 | 4240000 | 6.319341 |
| current68 /1 | 544000 | 0.489495 |
| current68 /2 | 544000 | 0.444399 |
| current68 /3 | 736000 | 0.749962 |

Backpressure recovery/drain is included before counter_end. Hotspot counter_end occurs before final conservation drain, so post-counter tail SQL/WAL cost is UNMEASURED. Counts/FE throughput inside120s plus full final asset conservation do not establish full-lifecycle cost. Per-server counter capture intervals and actual optional worker/batch/helper/WAL counters are retained; original WAL writes/bytes/barriers remain UNMEASURED, not0, and no baseline WAL reduction is claimed.

| Case | Median account SQL SUM_TIMER_WAIT seconds, original →68 | Change |
| --- | --- | --- |
| backpressure | 7.562138 → 14.230393 | 88.18% |
| hotspot | 45.120183 → 276.186464 | 512.11% |

SUM_TIMER_WAIT sums server-side elapsed across statements, workers and attempts, including lock waits and different statement mixes. It is not CPU time, full wall duration, single-query latency percentiles or whole backend-job time. The root observer is excluded from ct_dev counts; saved reports have no other live backend sessions.

All-phase independent event ledgers are preserved:original accepted/extracted230,400,000/230,400,000FE,current230,400,000/230,400,000FE. Latest per-channel checkpoint and separate zero SQL/local checks agree. Repeated cumulative checkpoints or mirrored SQL/WAL/local records are never summed. Given-load throughput/recovery is observer-limited evidence, not factory capacity.

Saved PID/server/world/session/epoch/argv match each cohort's preceding completed physical-container identity and selected launch manifests. Runtime87 vs exact68 remains distinct from checkout labels and historical753/4cfff0a evidence. Shared RCON reply bodies lack a business nonce; single observer/fixed events/static conservation checks passed without exact response-interleaving proof or demonstrated wrong FE timing/amount. End native/mod/barrier rings and avg100 snapshots have unknown coverage and are not whole-phase MSPT/TPS/percentiles.

Low-flow E2E is UNMEASURED(probes0). Frozen primary targets remain30% DB reduction per fixed240-input same/cross/mixed window,40% same upper-boundp95 reduction,cross upper-boundp95 regression at most20%; default10% descriptive flags are separate. New B/C primary results are assessed only from their complete reports.

Recompute offline: python3 scripts/analysis/compare-pressure-68f32db.py. This recipe reads sequence snapshots and saved reports only; no live workload/queries/observations or JFR parsing.

[Complete JSON](optimization-pressure-comparison-68f32db.json) · [All12 repeat CSV rows](optimization-pressure-comparison-68f32db.csv)
