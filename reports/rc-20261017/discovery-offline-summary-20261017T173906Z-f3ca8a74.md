Closed0113 follow-up descriptive evidence

FE old3647 → new0113, fixed/full actual same accepted inputs; frozen acceptance gates unchanged.

|layout|scope|tx old→new|SQL statements old→new|WAL writes old→new|
|---|---|---:|---:|---:|
|same|fixed|2346→2346|19678→19678|1199→1199|
|same|full|2357→2356|19732→19729|1201→1201|
|cross|fixed|3489→3482|22624→23180|1198→1200|
|cross|full|3504→3503|22699→23289|1200→1204|
|mixed|fixed|3126→3125|23630→23624|1318→1318|
|mixed|full|3140→3142|23702→23729|1320→1320|

New hour: 3600.0001010510023s actual input;20EP/6channels;30 pairs; all coverage gates true.

Actual accepted load differs from old hour; costs remain parallel, without normalized improvement claims.

- Frozen gates are unchanged and are NOT reassessed or overridden by this descriptive report.
- FE each layout n1, actual240 accepted inputs/7.68MFE; fixed output can differ, and fixed counters precede final drain. Full includes recorded drain/quiet.
- Sample conservation totals also include already-drained low-flow probes and warmup; they are not the steady-only7.68M counter input. Equality of those asset ledgers is checked without assigning them as counter-window input.
- Whole-MC and selected mod-root histograms are complete-window wall spans, not CPU timers, rolling averages, or uninstrumented GUI cost.
- Hour actual accepted vectors differ. Old/new hour costs are parallel values, never a same-business unit-cost improvement.
- Hour uses30 pairs, each32 A+32 B, only2 stable payload identities. Inherited base fixed_item_pair_per_observation_window describes pair composition, not total hour count; actual120s schedule/batches govern.
- Reason labels overlap and effective includes checkpoints. Actual devices/call and asset-bearing per-reason share remain UNMEASURED.
- One Python observer, conservative external bounds; no cross-JVM raw nanoTime subtraction or world-save latency claim.
- 20EP/6channels is not1000 capacity or peak factory throughput. RSS/GC observations do not prove no leak or pause percentiles.
- Shared SQL history was not reset; runs are sequential and n1 comparisons are descriptive, not statistical significance.

Scheduling JSON: `reports/rc-20261017/fe-scheduling-summary-20261017T173516Z-00e09eb271f3.json`
