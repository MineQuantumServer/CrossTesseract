# Original87 /68f32db physical vanilla-chest comparison

Both complete cohorts passed all six actual vanilla-chest probes:192 ordinary stones received per cohort,21 independent static guards, followed by confirmed output clearing and seven empty fixture removals. Conditions match exactly:two32-stone probes for same/cross/mixed,420s timeout,2.2s idle/quiet,0.1s read-only polling, endpointy64/EAST chest in the same forced chunk with64-block spacing. These are low-flow observations, separate from the30/120 primary FE workload and factory-capacity claims.

| Source | UTC start → end | Elapsed seconds | Runtime declared / checkout |
| --- | --- | --- | --- |
| original87 | 2026-10-06T14:18:19.004963+00:00 → 2026-10-06T14:41:15.020356+00:00 | 1376.015479 | 87bf217fcaffcceb2629c36bb54d5158b9f461e8 / 75392af252744f240253d134d1da565a49b2cc9f |
| current68 | 2026-10-06T17:04:40.551709+00:00 → 2026-10-06T17:06:30.265434+00:00 | 109.713807 | 68f32db439f445b8f72faf92dc62fbc5b9dce738 / 68f32db439f445b8f72faf92dc62fbc5b9dce738 |

Input is the validated item-replace request/reply interval; source is actual vanilla source chest decrease; output is actual vanilla destination chest acceptance. All bounds are single-observer durations within their own run. Source scan waiting and complete input-to-external-output time remain visible.

| Layout / ordinal probe | Input → source decrease (s), original →68 | Source → first output (ms), original →68 | Source → full32 (ms), original →68 | Complete input → external chest32 (s), original →68 |
| --- | --- | --- | --- | --- |
| same / 1 | 326.629–326.740 → 3.613–3.725 | 843.273–1057.215 → 103.242–311.740 | 843.273–1057.215 → 103.242–311.740 | 327.578–327.692 → 3.822–3.932 |
| same / 2 | 315.811–315.922 → 6.411–6.515 | 2196.591–2416.010 → 0.341–208.716 | 2196.591–2416.010 → 0.341–208.716 | 318.118–318.228 → 6.515–6.620 |
| cross / 1 | 6.773–6.885 → 3.420–3.527 | 5167.516–5389.429 → 104.638–316.790 | 5167.516–5389.429 → 104.638–316.790 | 12.051–12.164 → 3.630–3.738 |
| cross / 2 | 311.062–311.174 → 6.450–6.556 | 1332.749–1555.457 → 103.529–314.263 | 1332.749–1555.457 → 103.529–314.263 | 312.506–312.618 → 6.658–6.765 |
| mixed / 1 | 6.179–6.295 → 3.542–3.649 | 6863.242–7096.270 → 0.349–212.654 | 6863.242–7096.270 → 0.349–212.654 | 13.157–13.277 → 3.648–3.756 |
| mixed / 2 | 309.271–309.393 → 6.554–6.659 | 1695.429–1942.005 → 312.668–524.523 | 1695.429–1942.005 → 312.668–524.523 | 311.087–311.215 → 6.971–7.079 |

Current source→full upper bounds are below their paired original lower bounds for 6/6 observed pairs; current source→first has 6/6. Current complete input→full conservative bounds span3.629712–7.079332s, including source wait3.419893–6.659186s. Source→full spans0.341272–524.523274ms. First/full share observation intervals in12/12 probes:the first positive frame was already32, without proving atomic arrival.

Only two probes per layout are available. No p95/p99 population tail/capacity guarantee is claimed; those order statistics would simply be the observed maximum. Ordinal pairing uses separate fresh worlds without matching scanner phase, coordinates or initial schedule. Interval differences in JSON are observation arithmetic, not confidence intervals.

| Cohort / layout / probe | Actual external items by server | Total / final source |
| --- | --- | --- |
| original87 / same / 1 | {"A": 32} | 32 / 0 |
| original87 / same / 2 | {"A": 32} | 32 / 0 |
| original87 / cross / 1 | {"B": 32} | 32 / 0 |
| original87 / cross / 2 | {"B": 32} | 32 / 0 |
| original87 / mixed / 1 | {"A": 0, "B": 32} | 32 / 0 |
| original87 / mixed / 2 | {"A": 32, "B": 0} | 32 / 0 |
| current68 / same / 1 | {"A": 32} | 32 / 0 |
| current68 / same / 2 | {"A": 32} | 32 / 0 |
| current68 / cross / 1 | {"B": 32} | 32 / 0 |
| current68 / cross / 2 | {"B": 32} | 32 / 0 |
| current68 / mixed / 1 | {"A": 32, "B": 0} | 32 / 0 |
| current68 / mixed / 2 | {"A": 0, "B": 32} | 32 / 0 |

Each cohort delivered64 to its same/cross receiver and32 to each mixed receiver cumulatively. SQL pool, allocation remaining and all local item/FE/fluid buffers each independently checked zero in every guard; no mirrored SQL/WAL/local copies are summed as assets. Original passed21 guards/168 snapshots, quiet2.323996–2.493076s;68 passed21 guards/168 snapshots, quiet2.291251–2.374487s. Guards are sampled observations, not one atomic cross-JVM snapshot.

Counter windows cover both physical probes, all per-probe drain/clear guards and actual scanner waiting. Final modeOFF/identity validation/empty cleanup occur later. Longer original waits include more ambient/control/heartbeat work:these costs are not transfer-only or fixed120s/240-input primary costs. Layout costs repeat in the two individual-probe CSV rows as context and must not be summed across those rows.

| Layout | Actual counter capture seconds original /68 | DBtx original /68 | ct_dev account SQL events original /68 | Completed worker tasks original /68 |
| --- | --- | --- | --- | --- |
| same | 665.773660 / 29.718585 | 5912 / 154 | 41290 / 1428 | 405 / 27 |
| cross | 344.896821 / 29.656289 | 3091 / 162 | 21627 / 1503 | 214 / 29 |
| mixed | 345.357060 / 29.935146 | 3710 / 179 | 27595 / 1844 | 421 / 48 |

|68 layout | Instrumented Sql-helper attempts | Batch device appearances / records | WAL writes / bytes |
| --- | --- | --- | --- |
| same | 872 | 27 / 29 | 10 / 1774 |
| cross | 908 | 25 / 27 | 10 / 1774 |
| mixed | 1115 | 47 / 50 | 11 / 1997 |

Original Sql-helper/batch/WAL counts, bytes and barriers remain UNMEASURED, never0. Current WAL is measured only on68; no baseline WAL reduction is inferred. Per-JVM end-ring barrier/tick metrics have unknown coverage and do not establish phase-wide native MSPT/TPS or percentiles. Account SQL events count attempts/retries, exclude observer root, and both saved reports have no other live backend sessions. Container runtime errors/rejections/quarantines/deadlock retries and account SQL errors were0 in all six layout windows. Credit-publication counters include cross-server delivery and do not establish same-server-source fast hits.

| Cohort | Selected bytecode manifest SHA256 | Selected resource manifest SHA256 | ABC offline file rehash stable |
| --- | --- | --- | --- |
| original87 | 747021b11bfd2bd3d5c683aa30e633c1fdd3be134e899d0e0b0cff717ecc5540 | e668e6b54c3dfe8fea33fad3f29e1c44147b391dc17b3ca474952f50dae5fdea | True |
| current68 | 1068838aaf3f8f180752c2a078b7dc05600e398a0cbafe77477caacb9aba64ba | 2fbf78db6ad3e0c368cbab3760a29a0b90b9acb711f4ff6899d54a4ac2aee668 | True |

All12 saved selected launch class/resource folders were rehashed offline and match their recorded manifests. Actual FML paths, argfile hashes, classes/resources, PID/server/world/session/epoch and endpoint/chest coordinates are preserved in JSON and raw reports. The driver completed final PID/SQL identity/launch-file checks before empty cleanup; raw end PID replies remain, while distinct final SQL rows/hashes were not separately persisted. Selected launch assets and stable files are evidence, without a legacy class-loader CodeSource attestation. Original checkout HEAD differs from original runtime87; current declared revision and checkout both68f32db. Both recorded base-helper hashes match.

Original raw source:reports/optimization-container-container-original2-87bf217-20261006T141818Z-8488a9.json, SHA256212c6dc79e00989e48ae43e8d7b475d8fcbba780fc099ef91ea1f25dc2ce600a. Current raw source:reports/optimization-container-container-current-68f32db-68f32db-20261006T170440Z-f3e5f6.json, SHA256c4d88f785dc49c0dace4b309b556015270a9a2438a1045c9a49c3e162777d585. All68 values derive from this completed raw report;753 and4cfff0a results remain historical separate evidence.

The initial original ten-probe/120s attempt remains failed:reports/optimization-container-container-original-87bf217-20261006T140734Z-bfcb60.json, SHA25663fda22a693f8a7cd3468c33fc0d8ec51a4ad42dab71414518a908de28facaae. First same probe actually completed32; second preserved1164 frames all source32/target0, without a source decrease. Its E2E is UNMEASURED, not120s. Assets were retained; cross/mixed never ran. The later fresh two-probe420s successes do not erase the earlier failure. Operator source investigation attributed the wait to the original2s one-side/one-slot scanner and nominal324s slot0 revisit; source wait is separate from evidence of protocol asset loss.

One Python monotonic/RCON observer, no concurrent RCON sidecars, raw replies/coordinate checks and conservative request/read intervals are retained. Polling/read order/RCON overhead remain in bounds. Native shared reply bodies still lack business nonces; no wrong count/time is demonstrated. World-save, crash atomicity and other dimensions were not measured.

Frozen primary goals remain30% DB reduction per identical240-input same/cross/mixed window,40% same upper-boundp95 reduction,cross upper-boundp95 regression at most20%, with default10% descriptive flags separate. This physical supplement does not assess those goals. Core68 pressure began17:06:30 UTC after this container run; subsequent full primary B/C comparisons are separate evidence.

[Detailed paired JSON](optimization-container-comparison-68f32db.json) · [All12 probe rows](optimization-container-comparison-68f32db.csv)
