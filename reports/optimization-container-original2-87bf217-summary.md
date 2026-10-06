# Original87 physical vanilla-chest supplement

The original87 frozen launches completed all six probes: two each for same, cross and mixed, 32 ordinary stones per probe. Raw and offline checks passed, with 192 stones received and confirmed before clearing. The latest-code container comparison is **pending**; no current-code result is inferred here.

Complete source: `reports/optimization-container-container-original2-87bf217-20261006T141818Z-8488a9.json` (SHA256 `212c6dc79e00989e48ae43e8d7b475d8fcbba780fc099ef91ea1f25dc2ce600a`), 2026-10-06 14:18:19.004963–14:41:15.020356 UTC. One repeat, 420-second timeout, 2.2-second idle/quiet guards and 0.1-second configured polling. No warmup or sustained 30/120-second experiment.

All durations are conservative observation intervals from one Python monotonic clock. Input placement occurred inside the confirmed vanilla item-replace request/reply interval. Source timing starts at the observed physical source chest decrease. Input-to-full retains the preceding scanner wait.

| Layout / probe | Input → source decrease (s) | Source → first chest increase (ms) | Source → full32 external chest (ms) | Input → full32 (s) | Actual A / B stones |
| --- | --- | --- | --- | --- | --- |
| same / 1 | 326.629–326.740 | 843.273–1057.215 | 843.273–1057.215 | 327.578–327.692 | 32 / 0 |
| same / 2 | 315.811–315.922 | 2196.591–2416.010 | 2196.591–2416.010 | 318.118–318.228 | 32 / 0 |
| cross / 1 | 6.773–6.885 | 5167.516–5389.429 | 5167.516–5389.429 | 12.051–12.164 | 0 / 32 |
| cross / 2 | 311.062–311.174 | 1332.749–1555.457 | 1332.749–1555.457 | 312.506–312.618 | 0 / 32 |
| mixed / 1 | 6.179–6.295 | 6863.242–7096.270 | 6863.242–7096.270 | 13.157–13.277 | 0 / 32 |
| mixed / 2 | 309.271–309.393 | 1695.429–1942.005 | 1695.429–1942.005 | 311.087–311.215 | 32 / 0 |

Same-server probes waited about 327 and 316 seconds before source extraction; second cross/mixed probes waited about 311 and 309 seconds. The first cross/mixed probes waited about 6.8/6.3 seconds. These are reported observations. The operator traced the original nominal 324-second slot0 rotation (six sides × 27 slots × roughly two-second visits). Scanner phase explains sensitivity to input placement but does not replace the measured bounds.

Every first positive destination read already showed full32. Matching first/full observation intervals do not establish atomic arrival. Source observation spans were 105.941–120.360 ms and destination spans 108.001–126.216 ms, including polling, RCON and read order. Each elapsed interval uses `[max(0,t0-s1), max(0,t1-s0)]`. Input-to-full is derived directly; correlated component bounds are not added. JSON/CSV retain unrounded endpoints, observation widths, input command replies and frame references.

Same and cross sinks each received 64 stones. Mixed probe1 delivered 32 to B and zero to A; probe2 delivered 32 to A and zero to B. Both mixed receivers were served cumulatively, 32 each. This does not claim delivery to both on each probe.

All 21 drain proofs passed: before input, after full output, after confirmed clear for each probe, plus three final empty-cleanup guards. All 168 proof snapshots independently showed zero SQL pool, allocation remaining and six local item/FE/fluid buffer fields; source chest was empty and destinations held the guard's expected zero or32. Quiet guards lasted 2.323996–2.493076 seconds. SQL/WAL/local copies are never added to physical chest totals. Runtime errors, rejections, quarantines and deadlock retries all had zero deltas. All seven script-created empty device/chest fixtures were removed after successful checks.

Layout counters include scanner waits and guards: same/cross/mixed DB transaction deltas were 5912/3091/3710, and completed worker-task deltas were 405/214/421. They are not fixed steady windows or attributable per-probe transfer costs. Raw counter capture bounds and per-server deltas remain in JSON.

The initial ten-probe/120-second original attempt remains **failed**, in a separate world/session cohort: `reports/optimization-container-container-original-87bf217-20261006T140734Z-bfcb60.json` (SHA256 `63fda22a693f8a7cd3468c33fc0d8ec51a4ad42dab71414518a908de28facaae`). Its first same probe completed32 and drained/cleared, with source-to-full bounds 4873.477–5083.765 ms. The second probe timed out; all 1,164 frames showed source32 and target0, without source decrement. Its source-to-output E2E is **unmeasured**, not a completed 120-second latency. The last still-full source observation was conservatively at least 119.983 seconds after the confirmed input interval. Failure assets were retained; cross/mixed were never reached. This attempt is neither merged with the six successful probes nor relabeled as channel asset loss.

The complete run used fresh world-opt-container-original2-A/B/C and opt-container-original2-A/B/C identities. Saved PID, session/epoch, launch argfiles and FML manifests identify archived87 launch-selected assets despite checkout753. All three bytecode manifests agreed at `747021b11bfd2bd3d5c683aa30e633c1fdd3be134e899d0e0b0cff717ecc5540` under the container JSON recipe. The old harness has no class-loader CodeSource attestation; differently constructed manifests have different digest recipes.

Only two probes per layout were measured. Nearest-rank p95/p99 would both be the maximum; use individual bounds and the observed maximum, without claiming robust population tails, factory capacity or sustained production. The intended single RCON observer retained all 27,368 command records and coordinate-checked chest replies. The native shared response buffer has no command-specific body nonce; packet IDs alone do not prove body attribution. No wrong amount/timing is demonstrated by these saved results.

This supplement leaves the primary nine samples per mode, 40 FE probes, 30-second warmup/120-second steady scope and frozen goal misses unchanged. It does not measure world-save timing or cross-dimensional transfer.

[Detailed JSON](optimization-container-original2-87bf217-summary.json) · [six complete probes and two historical attempts in CSV](optimization-container-original2-87bf217-summary.csv)
