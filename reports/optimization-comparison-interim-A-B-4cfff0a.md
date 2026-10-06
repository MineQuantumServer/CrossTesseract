# Interim A/B optimization comparison

A is the completed immutable 87bf217 baseline; B is completed 4cfff0a with channel batching enabled and local fast path disabled. Both passed nine native FE samples with identical 40 probes, 30-second warmup and 120-second steady settings. C is still running and is excluded. Values below are medians of three independent repeats, not pooled latency percentiles.

The recorded latency spans real source capability acceptance to real target capability extraction using one Python observer and RCON lower/upper bounds. It is not a vanilla-container or world-save benchmark. See the [RCON source review](optimization-rcon-crosstalk-interim-A-B-4cfff0a.md) for the confirmed shared-buffer hazard and its evidence limits.

| Path | A upper p50/p95/p99 ms | B upper p50/p95/p99 ms | DB transactions A→B / 240 inputs | SQL account events A→B / 240 inputs | Worker tasks A→B |
| --- | --- | --- | --- | --- | --- |
| same | 2740.84/2866.16/2939.46 | 2227.69/2330.41/2354.84 | 3714→1969 (-46.98%) | 36589→22130 (-39.52%) | 682→627 |
| cross | 2745.21/2866.96/2937.47 | 2230.48/2340.50/2353.10 | 3657→1885 (-48.46%) | 35774→20925 (-41.51%) | 673→603 |
| mixed | 1930.39/2912.35/3402.30 | 2177.14/2345.50/2394.31 | 3614→2122 (-41.28%) | 31657→23976 (-24.26%) | 714→786 |

Every steady sample attempted and fully accepted exactly 240 × 32,000 FE. Worker tasks are not database transactions. Account-wide SQL events include controls; instrumented db_statements count Sql.query/update attempts, so these are separate scopes.

| B path | Sql-helper attempts | Batch device appearances / records | WAL writes / bytes | Identical WAL skips |
| --- | --- | --- | --- | --- |
| same | 14264 | 409 / 1042 | 574 / 131850 | 12 |
| cross | 13482 | 393 / 977 | 557 / 123445 | 11 |
| mixed | 15114 | 566 / 1016 | 687 / 123759 | 13 |

A WAL and new batch/Sql-helper counters are UNMEASURED. WAL resource copies are not added to SQL/local resources. Per-server barrier percentile snapshots are preserved in JSON as last-at-most-2048 journal barriers with unknown age; they are not full-phase p95 values. local_credit_publications also includes cross-server allocation delivery and cannot alone identify same-server-source fast hits.

| Frozen goal | Interim B result |
| --- | --- |
| DB transactions ≥30% reduction, same independently | 46.98% reduction; median goal met; all paired repeats met |
| DB transactions ≥30% reduction, cross independently | 48.46% reduction; median goal met; all paired repeats met |
| DB transactions ≥30% reduction, mixed independently | 41.28% reduction; median goal met; all paired repeats met |
| Same-server low-flow p95 ≥40% reduction | 18.69% reduction; goal missed |
| Cross-server low-flow p95 ≤20% regression | No regression; goal met |
| Idle transaction reduction and recovery/lifecycle integrity | Separate scale/correctness evidence; unmeasured by this FE comparison |

The original transaction goal remains per fixed external workload on each of same/cross/mixed. It has not been narrowed to only the faster local path.

Two descriptive regressions remain visible. Mixed low-flow upper p50 rose from 1930.39 to 2177.14 ms (+12.78%), despite better mixed p95/p99. Mixed maximum actual pull service gap rose from repeat values [3.00188, 3.49980, 3.00069] s to [5.00053, 3.50837, 4.99998] s: repeat median 3.00188→4.99998 s (+66.56%). This is the largest gap between successful pulls or phase boundaries, not a directly measured demand-pending wait. All mixed sinks received output; cumulative resource ledgers and independent local/SQL residue checks passed. B worker errors, rejected queues, quarantines, DB deadlock retries and SQL account errors were zero in steady windows.

Common A/B monitor coverage has 72 CPU/RSS and 72 heap/GC slices, over only eight cases: baseline same repeat 1 is absent; cross repeat 1 low-flow is partial. Slice endpoints, actual contained sample intervals, input ordinals, rejected samples and raw file hashes are in the sidecar summary. No interpolation fills missing time.

Common A/B tick slices are zero. The baseline tick sidecar covers only cross repeat 3 late low-flow/warmup/steady, while B stopped at 12:01:01 after the preserved wrong reply. Earlier successful B queries are retained individually; its metadata claim of all repeats is superseded by actual samples and failed status. Full-phase/whole-loop MSPT and actual TPS are UNMEASURED.

[Business comparison JSON](optimization-comparison-interim-A-B-4cfff0a.json) · [per-repeat CSV](optimization-comparison-interim-A-B-4cfff0a.csv) · [common monitor windows JSON](optimization-monitor-summary-interim-A-B-4cfff0a.json) · [monitor CSV](optimization-monitor-summary-interim-A-B-4cfff0a.csv) · [RCON exact extracts](optimization-rcon-crosstalk-interim-A-B-4cfff0a.json)
