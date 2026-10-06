# Original87 /753 pressure evidence

Both standalone pressure runs completed and passed all six windows, with identical declared conditions and complete per-repeat ledgers. The753 child exited0. Its parent sequence was deliberately interrupted and is **NOT_COMPLETED**:753 B/C never ran; new925 B/C is separate and pending. Parent interruption is not a failed pressure workload or evidence that the entire planned sequence completed.

Original source `reports/optimization-original-pressure-87bf217-20261006T144116Z-38d872.json` SHA256 `2eef02f7cf00467abb7db371e137e8edc814ea900734362692af422a6cfd9f8e`;753 source `reports/optimization-current-pressure-75392af-20261006T155117Z-09616b.json` SHA256 `03249f1501e7cbebccaab3f3e92864ea6911bf563fb35bcc2317d0c77cc9b566`. Reports, raw hashes and all12 repeat rows remain unchanged. Each case has30s warmup and three repeats. Backpressure uses240 inputs/7680000FE and120s intentional no-output hold; hotspot uses240 rounds across seven sources,1680 inputs/53760000FE.

| Case / repeat | Actual source events | DB transactions original →753 | ct_dev account SQL events original →753 | Completed worker tasks original →753 |
| --- | --- | --- | --- | --- |
| backpressure / 1 | 240 | 3103 → 2981 | 33677 → 49531 | 588 → 973 |
| backpressure / 2 | 240 | 3104 → 2852 | 34011 → 40859 | 583 → 889 |
| backpressure / 3 | 240 | 3052 → 2834 | 32778 → 39803 | 575 → 878 |
| hotspot / 1 | 1680 | 15109 → 9477 | 167838 → 158125 | 3939 → 5625 |
| hotspot / 2 | 1680 | 15219 → 9534 | 162270 → 158264 | 3967 → 5524 |
| hotspot / 3 | 1680 | 15527 → 9445 | 162676 → 155096 | 4038 → 5312 |

Backpressure repeat medians: DB3103→2852(-8.09%), but account SQL33677→40859(**+21.33%, default10% regression flag**). Worker tasks583→889(+52.49%) describe different scheduling work rather than successful DB transactions. Hotspot DB15219→9477(-37.73%), SQL162676→158125(-2.80%), worker tasks3967→5524(+39.25%). The hotspot reduction does not substitute for the frozen primary same/cross/mixed30% goal.

All original hotspot statement errors and deadlock retries are retained:281/191/149,621 total, with successful recovery and worker errors/rejections/quarantines0.753 has0 statement errors/retries in all six windows and0 worker errors/rejections/quarantines. Functional passes never erase the recovered original SQL failures. Every source's240 accepted32000-FE events and every receiver's actual amount are in JSON/CSV.

| Backpressure repeat | Recovery to verified drain seconds original →753 | First output reply-end delay ms original →753 |
| --- | --- | --- |
| 1 | 12.883601 → 13.011001 | 0.585098 → 0.852340 |
| 2 | 12.833468 → 12.299271 | 0.550136 → 0.571588 |
| 3 | 12.727364 → 12.344874 | 0.427122 → 0.542174 |

Recovery median12.833468→12.344874s(-3.81%). First output is extraction of already-held capability credit, not new input E2E; reply-end delay is not an exact mutation time. JSON/CSV reconstruct its conservative request/reply interval. The~122s successful-pull gap includes the deliberately disabled120s outputs and quiet guard, rather than proving starvation. Stable quiet held states show original localRX3872000/3616000/3904000FE with respective SQL pool3808000/4064000/3776000;753 localRX2048000 and SQL pool5632000 at every repeat. Allocation remaining mirrors those local credits and is retained independently, never added as another asset amount.

| Hotspot repeat / cohort | Every receiving endpoint's actual steady FE |
| --- | --- |
| 1 / original87 | hot_sink_0(A):5248000; hot_sink_1(B):7328000; hot_sink_2(B):6832000; hot_sink_3(C):7008000; cold0_sink_0(A):7456000; cold1_sink_0(B):7488000; cold2_sink_0(C):7456000 |
| 2 / original87 | hot_sink_0(A):7360000; hot_sink_1(B):5344000; hot_sink_2(B):6592000; hot_sink_3(C):7232000; cold0_sink_0(A):7552000; cold1_sink_0(B):7488000; cold2_sink_0(C):7552000 |
| 3 / original87 | hot_sink_0(A):5984000; hot_sink_1(B):6704000; hot_sink_2(B):6688000; hot_sink_3(C):7456000; cold0_sink_0(A):7584000; cold1_sink_0(B):7520000; cold2_sink_0(C):7584000 |
| 1 / current753 | hot_sink_0(A):7648000; hot_sink_1(B):7584000; hot_sink_2(B):7552000; hot_sink_3(C):7552000; cold0_sink_0(A):7648000; cold1_sink_0(B):7616000; cold2_sink_0(C):7616000 |
| 2 / current753 | hot_sink_0(A):7648000; hot_sink_1(B):7584000; hot_sink_2(B):7520000; hot_sink_3(C):7584000; cold0_sink_0(A):7648000; cold1_sink_0(B):7616000; cold2_sink_0(C):7616000 |
| 3 / current753 | hot_sink_0(A):7616000; hot_sink_1(B):7584000; hot_sink_2(B):7520000; hot_sink_3(C):7552000; cold0_sink_0(A):7648000; cold1_sink_0(B):7616000; cold2_sink_0(C):7616000 |

All seven hotspot sinks were served in every repeat. Median maximum successful-pull gap6.007117→2.004643s; median output409332.293→443466.261FE/s(+8.34%) under supplied448000FE/s input. This is given-load delivery, not factory capacity. Old post-window tails were4944000/4640000/4240000FE;753 tails544000/544000/608000FE were actually drained afterward. Last per-channel checkpoints and independent all-phase ledgers match:each cohort230,400,000FE accepted/extracted. Cumulative repeat checkpoints and SQL/WAL/local copies are never summed.

Backpressure includes recovery/drain before counter_end. Hotspot and normal primary paths capture counter_end before final conservation drain; tail SQL/WAL cost is unmeasured. More assets delivered inside120s or full final conservation does not establish full-lifecycle cost. Counter capture intervals, root-excluded account statement scope, per-server actual instrumented counters and end-ring diagnostics are retained. Original WAL/helper/batch counts are UNMEASURED, not0;753 WAL counters do not establish a before/after WAL reduction.

Account SQL SUM_TIMER_WAIT also increased and remains visible:

| Case | Median summed statement elapsed seconds original →753 | Change |
| --- | --- | --- |
| backpressure | 7.562138 → 20.649723 | +173.07% |
| hotspot | 45.120183 → 241.719894 | +435.72% |

These are server-side elapsed sums across statements/workers, including attempt/lock-wait and statement-mix changes; they are not CPU usage, wall duration, single-statement latency percentiles or full backend-job time. The derived median default flag and every paired descriptive increase are retained alongside functional success. Raw mod/delivery/SQL/barrier end-ring snapshots have unknown age and are not whole-phase/native MSPT/TPS comparisons.

All12 drive/hold phases had240 scheduled/planned rounds,late_rounds0 and observer_saturated=false. Saved PIDs/world/session/epoch/argv match each preceding physical-container cohort's frozen assets, linking runtime87 and exact753 despite original checkout753. No future925 result is inferred. The original shared RCON body-buffer/nonce limitation persists; one observer, fixed events and independent resource checks passed without proving missing raw per-command attribution.

JDK/JFR offline parsing was already complete before the753 measurements:operator-recorded15:48:31–15:48:35 UTC; saved parsed-JSON generated_utc is2026-10-06T15:48:34.895675Z. Container began15:49:28, pressure15:51:17. The operator reports no new JDK/profile/raw-JFR work during pressure. This report only reads parsed metadata; it neither parses JFR nor claims continuous whole-system process exclusion. The stop-audit references that earlier diagnosis as the reason to defer B/C.

Frozen targets remain30% per primary same/cross/mixed fixed240-input counter window,40% same upper-boundp95 reduction,cross upper-boundp95 max regression20%; default10% descriptive flags are separate. Pressure has no isolated low-flow E2E distribution and cannot replace those goals.925 primary/scale results remain separate pending evidence.

[Complete JSON](optimization-pressure-comparison-75392af.json) · [all12 repeat rows/receiver/source ledgers in CSV](optimization-pressure-comparison-75392af.csv)
