# Completed A/B/C FE comparison

All 27 samples passed input, event-ledger, receiver-service and independent SQL/local-buffer residue checks. Each mode accepted and extracted 86,768,640 FE across all phases. Every steady sample attempted and fully accepted 240 × 32,000 FE after 30 seconds of warmup; low-flow used 40 isolated 1024-FE probes per path/repeat. Values below are medians of three repeat statistics, not pooled percentiles.

**Revision boundary:** A used immutable 87bf217 launch classes. Measured B/C code was exactly 4cfff0a (recorded artifact SHA256 `4cd0d4b7be1a30946ebfbb72cc554962ce7655d8bb8218797d8a0d07e95a2859`). B enabled channel batches and disabled local fast path; C enabled both. Later closing-only e4057a5 correctness/artifact results do not change this timing provenance. Subsequent physical-container/scale results must keep their own version and scope. Original PID/session/epoch records, operator config/artifact snapshots and raw file hashes are in JSON; the old harness did not attest a loaded class hash.

| Path | A upper p50/p95/p99 ms | B upper p50/p95/p99 ms | C upper p50/p95/p99 ms |
| --- | --- | --- | --- |
| same | 2740.84/2866.16/2939.46 | 2227.69/2330.41/2354.84 | 203.74/217.19/244.35 |
| cross | 2745.21/2866.96/2937.47 | 2230.48/2340.50/2353.10 | 306.19/407.78/412.92 |
| mixed | 1930.39/2912.35/3402.30 | 2177.14/2345.50/2394.31 | 208.05/410.25/415.78 |

These are actual source capability acceptance → actual target capability extraction, bracketed by one Python observer’s RCON intervals. They are not vanilla chest, world-save, different-dimension or factory-capacity measurements. Fixture Tesseracts may occupy the same chunk; NeighborPump skips adjacent Tesseracts.

| Path | DB transactions A / B / C | SQL account events A / B / C | Worker tasks A / B / C |
| --- | --- | --- | --- |
| same | 3714 / 1969 / 2426 | 36589 / 22130 / 31737 | 682 / 627 / 793 |
| cross | 3657 / 1885 / 3492 | 35774 / 20925 / 39984 | 673 / 603 / 1359 |
| mixed | 3614 / 2122 / 3256 | 31657 / 23976 / 41352 | 714 / 786 / 1331 |

Counters cover the actual existing per-server status snapshot intervals, including control/heartbeat work. Worker tasks are separate from successful DB transactions. Account SQL events count statement/sql attempts including controls/retries; Sql-helper counters count query/update helper attempts and are a different scope. Other live backend sessions were empty in all three reports.

| Frozen goal against A | B | C |
| --- | --- | --- |
| ≥30% DB reduction per fixed workload, same independently | 46.98% reduction; met | 34.68% reduction; met |
| ≥30% DB reduction per fixed workload, cross independently | 48.46% reduction; met | 4.51% reduction; **missed** |
| ≥30% DB reduction per fixed workload, mixed independently | 41.28% reduction; met | 9.91% reduction; **missed** |
| Same-server low-flow p95 ≥40% reduction | 18.69%; **missed** | 92.42%; met |
| Cross-server low-flow p95 ≤20% regression | 18.36% improvement; met | 85.78% improvement; met |
| Idle DB reduction and full lifecycle/recovery integrity | Separate scale/native correctness evidence | Separate scale/native correctness evidence |

C does **not** meet the original 30% DB goal on cross or mixed paths. This generic fixed-workload goal has not been restricted to same-server traffic after seeing the data. JSON also retains every paired-repeat reduction: all three C cross/mixed repeats miss 30%.

| B→C path | Sql-helper attempts | Batch device appearances / records | WAL writes | WAL bytes | Worker tasks |
| --- | --- | --- | --- | --- | --- |
| same | 14264→20807 | 409/1042→793/1354 | 574→1200 | 131850→202728 | 627→793 |
| cross | 13482→25493 | 393/977→879/1398 | 557→1319 | 123445→216175 | 603→1359 |
| mixed | 15114→26260 | 566/1016→1211/1691 | 687→1439 | 123759→229735 | 786→1331 |

A WAL/batch/Sql-helper counts are UNMEASURED, not zero. B→C WAL write increases are 109.06% / 136.80% / 109.46%; byte increases 53.76% / 75.12% / 85.63%; task increases 26.48% / 125.37% / 69.34% (same/cross/mixed). Per-JVM barrier p50/p95/p99 snapshots are retained as last-at-most-2048 completed barriers with unknown age; no phase-wide percentile or subtraction of percentiles is claimed. local_credit_publications includes cross-delivery credit publication, so it is not a same-server-source fast-hit count.

All descriptive regressions from the offline checker remain in JSON: A→B has mixed upper p50 +12.78% and largest actual pull service gap +66.56% (3.00188→4.99998 s); A→C has SQL account events +11.77% cross and +30.63% mixed. B→C has increases on all three paths in DB commits/attempts, SQL account events, Sql-helper attempts, WAL writes and WAL bytes (18 cost flags at the unchanged 10% comparison threshold). Worker/device/record counts are retained as diagnostics. C reduces largest service-gap medians to 0.52499 / 0.54057 / 1.03536 s, with both mixed receivers served near 50/50. Service gaps are between successful pulls or phase boundaries, not directly measured demand-pending wait times.

Steady B/C worker errors, rejected queues, quarantines, SQL account errors and DB retries were zero; A mixed repeat 1 had one recovered DB retry/account statement error. No SQL/WAL/local resource copies are added in conservation. The lower tail remaining at steady cutoff is drained and audited separately.

The native shared RCON reply-buffer hazard and B tick failure are preserved in the [offline source review](optimization-rcon-crosstalk-interim-A-B-4cfff0a.md). The exact failure interleaving was not captured. The FE driver is the only FE writer, push/pull handlers are synchronous, passive observers cannot emit ACCEPTED/EXTRACTED, and marker/input/conservation checks passed. No observed wrong FE amount or timing is proven; complete raw business replies/request-specific body tags were not saved, so every attribution cannot be independently reconstructed. This limitation does not make all recorded latency false.

[Complete comparison JSON](optimization-comparison-4cfff0a.json) · [per-repeat CSV](optimization-comparison-4cfff0a.csv) · [monitor coverage](optimization-monitor-comparison-4cfff0a.md)
