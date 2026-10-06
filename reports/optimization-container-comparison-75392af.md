# Original87 / current753 physical vanilla-chest comparison

Both complete runs passed all six physical probes and independent resource guards. Each moved192 ordinary stones, then cleared only confirmed output and removed seven empty fixtures. The same declared conditions used two32-stone probes per same/cross/mixed layout,420s timeout,2.2s idle/quiet and0.1s polling. This is a low-flow supplement, not the primary30/120 FE experiment or a factory-capacity/tail guarantee.

Each table entry shows original → current conservative bounds. Input is the actual item-replace request/reply placement interval; source is actual physical source-chest decrease, and output is real vanilla-chest acceptance. Source scan waiting and full input-to-arrival remain visible.

| Layout / ordinal probe | Input → source decrease (s) | Source → first output (ms) | Source → full32 output (ms) | Full input → chest32 (s) |
| --- | --- | --- | --- | --- |
| same / 1 | 326.629–326.740 → 3.409–3.519 | 843.273–1057.215 → 212.030–422.161 | 843.273–1057.215 → 212.030–422.161 | 327.578–327.692 → 3.726–3.836 |
| same / 2 | 315.811–315.922 → 6.307–6.414 | 2196.591–2416.010 → 102.964–312.096 | 2196.591–2416.010 → 102.964–312.096 | 318.118–318.228 → 6.516–6.621 |
| cross / 1 | 6.773–6.885 → 3.642–3.751 | 5167.516–5389.429 → 209.593–420.369 | 5167.516–5389.429 → 209.593–420.369 | 12.051–12.164 → 3.957–4.066 |
| cross / 2 | 311.062–311.174 → 6.124–6.231 | 1332.749–1555.457 → 208.519–418.665 | 1332.749–1555.457 → 208.519–418.665 | 312.506–312.618 → 6.438–6.544 |
| mixed / 1 | 6.179–6.295 → 3.549–3.655 | 6863.242–7096.270 → 0.330–210.790 | 6863.242–7096.270 → 0.330–210.790 | 13.157–13.277 → 3.654–3.761 |
| mixed / 2 | 309.271–309.393 → 6.190–6.296 | 1695.429–1942.005 → 211.886–424.336 | 1695.429–1942.005 → 211.886–424.336 | 311.087–311.215 → 6.507–6.615 |

All six current source-to-output upper bounds are below their paired original lower bounds in these observations. First/full32 share observation intervals because the first positive chest read already contained32; this does not prove atomic arrival. Current input-to-full conservative bounds span 3.654–6.621s, including source waits of 3.409–6.414s. Do not report only the shorter source-to-output interval. Pairing is by ordinal in new worlds, without synchronizing scanner phase or claiming a randomized matched experiment.

Same/cross each delivered64 to their single receiver in each cohort. Original mixed probe1 delivered A0/B32, probe2 A32/B0; current mixed probe1 A32/B0, probe2 A0/B32. Each mixed receiver received32 cumulatively in both runs. Every probe had exactly32 total output and source-empty, then separate zero checks for SQL pool, allocation remaining and all local item/FE/fluid buffers. Each cohort passed21 guards/168 snapshots; original quiet durations were2.323996–2.493076s, current values remain unrounded in JSON. Both cleared192 confirmed stones and removed seven empty fixtures. These are repeated sampled guards, not an atomic cross-JVM snapshot.

Counter windows cover each two-probe layout, guards and actual wall-time scanner waiting. Final modeOFF/identity validation/empty cleanup occur later. Original scanner waits create much longer windows; these counts are not fixed120s/240 inputs, transfer-only cost or proof of the frozen primary30% DB goal. Layout counts repeat as context in each probe CSV row and must not be summed across those rows.

| Layout | Counter capture seconds original / current | DBtx original / current | ct_dev account statements original / current | Completed worker tasks original / current |
| --- | --- | --- | --- | --- |
| same | 665.773660 / 29.655926 | 5912 / 153 | 41290 / 1431 | 405 / 26 |
| cross | 344.896821 / 29.876050 | 3091 / 167 | 21627 / 1558 | 214 / 30 |
| mixed | 345.357060 / 29.876163 | 3710 / 179 | 27595 / 1844 | 421 / 48 |

| Current layout | Instrumented Sql-helper attempts | Batch device appearances / records | WAL writes / bytes |
| --- | --- | --- | --- |
| same | 864 | 26 / 29 | 11 / 1997 |
| cross | 944 | 26 / 30 | 12 / 2220 |
| mixed | 1115 | 47 / 50 | 11 / 1997 |

Original Sql-helper/batch/WAL keys are UNMEASURED, including WAL bytes/barriers; they are not zeros and no WAL before/after reduction is claimed. Current barrier percentiles are per-server end-ring snapshots with unknown window age. Account statements include retries and controls, not JDBC round trips; the root observer account is excluded. Both reports saved no other live backend sessions. Runtime errors/rejections/quarantines/deadlock retries and account statement errors were zero in both container runs. Cross `local_credit_publications` includes remote allocation delivery and must not be labeled a same-server-source fast hit. SQL/WAL/local mirrors are never added as physical assets.

| Cohort | Selected bytecode manifest SHA256 | Selected resource manifest SHA256 | All ABC offline rehashes match |
| --- | --- | --- | --- |
| original87 | 747021b11bfd2bd3d5c683aa30e633c1fdd3be134e899d0e0b0cff717ecc5540 | e668e6b54c3dfe8fea33fad3f29e1c44147b391dc17b3ca474952f50dae5fdea | True |
| current753 | a23ed9b16c363f741349d5565480bf07de680ad1648e1190cf62bcfea215d525 | 2fbf78db6ad3e0c368cbab3760a29a0b90b9acb711f4ff6899d54a4ac2aee668 | True |

Actual saved FML paths point to each cohort's frozen scratch/dev-launch directories; full argfile hashes, manifests, PIDs/worlds/session/epoch and coordinates are in JSON/raw reports. The driver rechecked PID, SQL identity and class/resource hashes before cleanup. This offline analysis also rehashed all12 immutable launch folders, matching saved manifests. Raw final PID replies exist; separate final SQL rows/manifest hashes were not persisted. These checks identify selected launch assets, without a legacy JVM class-loader CodeSource attestation or treating checkout HEAD as loaded code. Both base-helper hashes are identical.

Original source `reports/optimization-container-container-original2-87bf217-20261006T141818Z-8488a9.json` SHA256 `212c6dc79e00989e48ae43e8d7b475d8fcbba780fc099ef91ea1f25dc2ce600a`; current source `reports/optimization-container-container-current-75392af-20261006T154928Z-38ab4f.json` SHA256 `d465e1ac20a4c623bc40f1fc6b8fd47bfe8102b1c3441605608d6bcb2e084eb4`. All raw bodies and original boundaries remain unchanged. Elapsed original/current totals were1376.015479/108.943274s, including setup/guards/cleanup, not sustained throughput.

The initial ten-probe/120-second original attempt remains failed and separate: `reports/optimization-container-container-original-87bf217-20261006T140734Z-bfcb60.json` SHA256 `63fda22a693f8a7cd3468c33fc0d8ec51a4ad42dab71414518a908de28facaae`. Its first same probe completed32; second had all1,164 observed frames source32/target0 and no source decrement. That E2E is UNMEASURED, not120s. Failure assets were retained, cross/mixed were not run, and the later two-probe420s cohorts do not erase this result.

Only two probes per layout are available; p95/p99 would merely be the maximum. Individual interval arithmetic in JSON is not a confidence interval or population tail estimate. Each run used one Python monotonic RCON observer and no parallel sidecars; bounds include polling/read order/round trips. Native shared reply bodies still lack request-specific nonces, despite coordinate checks; no wrong count/time is demonstrated. There is no world-save, crash-atomicity or cross-dimensional guarantee.

The primary same/cross/mixed30% fixed-input-window DB goal, samep95 reduction40%, crossp95 max regression20%, and separate default10% descriptive flags are unchanged and not assessed from this supplement. The operator paused the sequence during753 pressure before a later hotfix and new-core B/C; those primary comparisons remain pending. This completed physical-container result is exact753 and does not measure the future hotfix. Historical4cfff0a results remain historical.

[Detailed paired JSON](optimization-container-comparison-75392af.json) · [all12 individual probe rows](optimization-container-comparison-75392af.csv)
