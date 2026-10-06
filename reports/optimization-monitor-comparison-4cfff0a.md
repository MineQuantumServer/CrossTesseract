# A/B/C common monitor coverage

This file compares only contained real observations matched by scenario/repeat/phase and input ordinal. The benchmark recorded a second-resolution UTC origin rather than an absolute observer monotonic origin: alignment is approximate with an explicit ±1-second margin. CPU/GC differences use actual contained first/last readings, not interpolated phase boundaries. Every raw file SHA256, read interval and sample reference remains in JSON. Timings correspond to 87bf217 / 4cfff0a; later closing-only e4057a5 is not retroactively measured.

| Runs sharing the slice | CPU/RSS slices | Heap/GC slices | Native tick-query slices |
| --- | --- | --- | --- |
| A+B+C | 72 | 72 | 0 |
| A+B only | 72 | 72 | 0 |
| A+C only | 72 | 72 | 6 |
| B+C only | 81 | 81 | 30 |

A lacks process sampling for all of same repeat 1, and cross repeat 1 low-flow is partial. Thus the three-run CPU/heap comparison covers only eight cases, with low/warm/steady retained as separate slices. Point-span hulls are not continuous heap/tick coverage. B/C full process reports do not repair missing A time.

B tick sidecar failed at 2026-10-06T12:01:01.331510+00:00: server B `tick query` returned `EXTRACTED 0`. Verbatim failure: `B: ValueError: Unrecognized tick query response; raw reply retained`. It stopped with 495 samples. C tick sidecar completed with 681 samples. A tick observations exist only in cross repeat 3 late low-flow/warmup/steady; B had already stopped by that corresponding stage. Therefore **no common three-mode native tick window exists**, and A+B native tick is UNMEASURED. Pair-only observations below cannot be promoted into three-way evidence.

| Shared steady source-JVM A slice | Repeats | CPU % A / B / C | Heap-used sample-mean MiB A / B / C | GC GCT delta seconds A / B / C |
| --- | --- | --- | --- | --- |
| same | 2,3 | 9.83 / 9.75 / 11.35 | 333.96 / 417.39 / 330.77 | 0.013 / 0.006 / 0.008 |
| cross | 1,2,3 | 8.36 / 9.00 / 9.85 | 368.59 / 442.25 / 328.87 | 0.006 / 0.000 / 0.009 |
| mixed | 1,2,3 | 9.12 / 9.87 / 10.87 | 348.57 / 399.76 / 326.95 | 0.007 / 0.011 / 0.016 |

These are medians of matched sampled slices for server A only, not total cluster CPU or complete 120-second phases. Actual CPU counter spans here are approximately 100–105 seconds. One CPU is 100%; values include all JVM threads/ambient work. Heap means contain uncollected objects; GCT includes concurrent elapsed work and is not a STW pause percentile. Tick-sidecar availability/load differs after B’s failure, so these process comparisons are diagnostic rather than an isolated attribution of mod CPU.

| A↔C pair-only cross repeat 3 native queries | Server | Queries A / C | Mean of queried recorded-tick window means ms A / C |
| --- | --- | --- | --- |
| low_flow | A | 8 / 4 | 0.3000 / 0.4250 |
| low_flow | B | 8 / 4 | 0.3125 / 0.4000 |
| low_flow | C | 8 / 4 | 0.2000 / 0.2000 |
| steady | A | 8 / 8 | 0.4000 / 0.4875 |
| steady | B | 8 / 8 | 0.3875 / 0.4750 |
| steady | C | 8 / 8 | 0.2000 / 0.2250 |

Each query describes the vanilla last-100 recorded work ticks, rounded roughly ±0.05 ms. Unknown window age means even the 10-second head guard does not prove all 100 ticks belong to this stage. These are means of query-window means, not phase-wide tick percentiles or whole-loop MSPT. Target 20 ticks/sec is not a measured actual TPS. B↔C has 30 separate pair-only query slices inside B’s actual earlier coverage; exact intervals and sample references are in JSON/CSV.

[Coverage JSON](optimization-monitor-comparison-4cfff0a.json) · [CSV with individual/common/pairwise scope](optimization-monitor-comparison-4cfff0a.csv) · [FE comparison](optimization-comparison-4cfff0a.md)
