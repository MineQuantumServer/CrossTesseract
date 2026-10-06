# Original / failed e405 / current753 scale evidence

75392af completed all six nominal 120-second OFF/ACTIVE measurements and passed its endpoint/error/rejection/quarantine acceptance gate. The e405 run remains failed: 500 ACTIVE had 50 errors; 1000 ACTIVE had 496 errors, an initial active count of 992 and a final count of 984. Its raw `passed:true` only meant the old procedure completed; the separate audit is false. Current 753 uses the archived artifact SHA256 `fc7a072581630ed39125d6bf00d362df5e51200f6dabc40c85a47d98b16975e8`; the earlier 27 ABC samples remain exact 4cfff0a. Saved PID/starttime/argv hashes and operator artifact records are in JSON; the legacy harness has no class-loader source attestation.

One Minecraft 1.21.1/Neo 21.1.252 Java 21 JVM, isolated dev_perf_v1 MySQL 8.4.7/Redis 7.4.6, four channels, 3×2 loaded chunks at current x=30357, 5 seconds of warmup, 120 nominal steady seconds and one repeat. The source reports retain actual counters and hardware. The original raw report did not record its x-coordinate or geometry; the operator independently checked the matching six-chunk footprint.

| Count |753 OFF DBtx / nominal tx/s |753 ACTIVE DBtx / nominal tx/s | Actual output FE/s original /753 | ACTIVE errors e405 /753 |
| --- | --- | --- | --- | --- |
|100|182 / 1.516665|5512 / 45.933300|159374.86 / 160908.22|0 / 0|
|500|241 / 2.008332|7517 / 62.641615|154208.03 / 155349.87|50 / 0|
|1000|362 / 3.016664|9662 / 80.516603|155533.23 / 158916.54|496 / 0|

753 OFF worker-task deltas were0 at every scale. Its first/final active counts were exactly100/500/1000; all contained ACTIVE sidecar samples also matched their scale count. The original and753 raw ACTIVE inputs each total19,200,000 FE per nominal interval; e405 inputs differ. These totals are preserved without claiming matched individual input events, identical initial buffers or identical read boundaries. Extraction can exceed interval input because warmup assets and tail capture remain. No independent final asset-drain audit or per-receiver output ledger exists in this scale driver.

Only16 fixture capability calls are made per Minecraft tick, giving a nominal160,000-FE/s input ceiling if the server runs20ticks/s. Output changes are only+0.96%/+0.74%/+2.18% at100/500/1000 under this supplied load. This does not measure factory capacity, physical-container transfer or overload saturation.

**Main-thread mod time regressed substantially.** The native harness reports `tick_ms` from RuntimeService.tick, not the whole Minecraft loop. These are last-at-most2048 ring snapshots, not complete120s percentiles.

| ACTIVE count | Mod tick p95 ms original →753 | Change | Mod tick p99 ms original →753 |
| --- | --- | --- | --- |
|100|0.367662 → 0.717687|+95.20%|0.813862 → 1.131528|
|500|0.467230 → 1.590095|+240.32%|0.826755 → 2.401132|
|1000|0.576145 → 2.668976|+363.25%|1.117527 → 4.510519|

At 100 endpoints, dispatch-to-credit delivery p95/p99 rose 41.75%/12.12%. Whole backend worker-job `sql_ms` p95 rose 109.91%/167.90%/386.62% at 100/500/1000; batched jobs contain more work, so this does not measure single SQL-statement latency. OFF mod tick p95 also rose 52.83%/19.00%/5.33%. All 27 original→753 timer increases above 10% are retained in JSON.

Whole-Minecraft `getAverageTickTimeNanos` recorded-work avg100 snapshots exist only on later code: current753 ACTIVE final0.878065/1.348930/1.822731ms. Window age is unknown and the original has no equivalent; before/after whole-Minecraft MSPT/TPS is UNMEASURED. The target20ticks/s is not measured actual TPS.

| Actual sampled DB window | Original Δtx / seconds / tx/s |753 Δtx / seconds / tx/s | Scope |
| --- | --- | --- | --- |
|1000 OFF|862 / 118.000201 / 7.305072|356 / 118.000048 / 3.016948|Observed OFF; excludes later cleanup|
|1000 ACTIVE|75994 / 117.998892 / 644.022995|9482 / 117.999638 / 80.356178|Observed1000 ACTIVE|
|500 ACTIVE|26217 / 45.995537 / 569.990079|2971 / 46.000770 / 64.585876|Late24-point tail only|

Observed1000 OFF DB rate fell58.70%, meeting the frozen30% idle goal within this sampled scope. Observed1000 ACTIVE rate fell87.52%. These are actual~118s counter spans, not invented full120s differences. Earlier original100/500 OFF DB windows are UNMEASURED. The original raw report lacks first_metrics everywhere; adjacent phase-final cumulative values cannot replace them. No native scale result replaces the earlier ABC cross/mixed fixed-workload goal misses.

Window selection is explicit: original1000 OFF rounds33–92 (10:01:27.189856–10:03:25.192562 UTC) and ACTIVE95–154 (10:03:31.189909–10:05:29.191859);753 OFF257–316 (14:00:20.208734–14:02:18.211567) and ACTIVE320–379 (14:02:26.208764–14:04:24.211140). Original500 only rounds0–23 (10:00:21.189569–10:01:07.193350), matched to753225–248 (13:59:16.208664–14:00:02.211872). Logical cutoff alignment is approximate; actual request/reply/counter bounds are saved without interpolation or cross-JVM clock subtraction.

e405 nominal OFF500/1000 still completed1368/2931 tasks. Its1000 post-reset monitored ACTIVE had482 errors and active range912–992; all60 points were below1000. Its500 failed window includes every full/partial-active observation rather than selected error-free fragments. Initial failed-monitor ERROR backend_error is preserved; cleanup windows are excluded from idle goals. 7531000 OFF transient ready-device values0–8 remain visible, despite zero completed worker tasks and zero sampled worker queue/admitted completions.

|753 ACTIVE count|Sql-helper attempts|Worker tasks|Batch device appearances / records|WAL writes / bytes|
| --- | --- | --- | --- | --- |
|100|109455|2257|9432 / 10566|9808 / 1545888|
|500|179495|4020|17448 / 18174|17618 / 2618186|
|1000|256433|5916|26392 / 27322|24889 / 3679713|

Original Sql-helper and WAL counters are UNMEASURED. Helper attempts are not account statement/sql events or JDBC controls; worker tasks are not DB transactions, and batch devices are appearances rather than distinct devices. Commit/attempt differences can straddle in-flight work. SQL, WAL and local copies are never added as resource amounts. CPU/heap/GC evidence is restricted to contained real samples with raw hashes and capture bounds; GCT is not a STW pause percentile. There are no full-phase monitoring claims.

RCON uses a shared native reply buffer without a body nonce. Raw sidecar replies are retained; protocol IDs do not independently attest bodies, and the old business driver did not retain every raw reply. No incorrect FE amount/time is proven, but per-event attribution cannot be reconstructed from these aggregate reports. Subsequent positive-allocation-guard EXPLAIN failures/retries are untimed diagnosis and do not enter steady rates. Historical excluded/truncated tiny exponent fields remain unmeasured; the historical reports are not rewritten.

[Complete JSON](optimization-scale-comparison-75392af.json) · [nominal/sampled CSV](optimization-scale-comparison-75392af.csv) · [failed e405 evidence](optimization-scale-comparison-e4057a5.json)
