# Offline optimization comparison

| Evidence | Value |
| --- | --- |
| Aggregate input | /workspace/reports/optimization-comparison-68f32db.json |
| Aggregate SHA-256 | 64d9041979a4bb54e66082852f4ef90dfadaea5b979e9524798d5444e1e1a58e |
| Aggregate bytes | 1246999 |
| Aggregate recorded UTC | 2026-10-06T18:53:12.775919+00:00 |
| Renderer SHA-256 | 77bd6d940ce8825febcabae64419a149e426da58d368e01dfff3b89a7451cc2a |

This renderer ran no Minecraft, backend, fault, native, performance or profiling tests: NOT RUN by this tool. Driver statuses are supplied evidence; functional passed does not mean frozen performance goals were met.

## Measurement boundaries

Latency numbers are medians of per-repeat full_output p50/p95/p99, with separate RCON lower/upper bounds; they are not pooled percentiles. full_output ends when the probe's accepted asset has been fully pulled, using its last successful pull. It does not establish service to every configured recipient on every probe.

Main-path SQL/WAL/worker counters end before the final conservation drain. Steady extraction can lag accepted input; tail work is not added to the fixed input window. Final conservation is reported separately and cumulatively for reused channels. Backpressure recovery, if present, follows its recorded counter scope.

Account statement events differ from Sql-helper attempts; completed worker tasks differ from SQL commits. Batch devices/records are appearances, not distinct devices or batch calls. Total batch calls remain UNMEASURED unless explicitly captured. Missing original WAL counters are UNMEASURED, not zero.

Recipient max pull gaps are gaps between successful pulls and phase boundaries, not measured demand-pending waits or a latency bound. Jain indices describe observed outputs and do not establish a fairness guarantee. WAL ring percentiles are per-JVM diagnostic snapshots with unknown window age; do not subtract, pool or call them phase-wide timings.

Raw git_head is preserved as reported workspace metadata. Explicit sequence evidence can provide an operator-declared runtime revision bound by exact child SHA; it is not classloader attestation. Without that evidence no runtime revision is inferred from a label.

No actual TPS or complete wall-clock MSPT is inferred. Comparison regression flags are descriptive hints, not additional frozen acceptance goals.

## Profile identity and recorded status

| Profile | Recorded state | Driver source | Driver SHA-256 | Raw workspace HEAD | Declared runtime revision | Identity evidence |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | passed | reports/optimization-original-final-87bf217-20261006T145840Z-0d4630.json | 35700d3cfff60022c381f38fab52a3d3daf745b842b1e29309a9cf68a1c5a676 | 75392af252744f240253d134d1da565a49b2cc9f | 87bf217fcaffcceb2629c36bb54d5158b9f461e8 | VERIFIED_SEQUENCE_REFERENCE |
| batch | passed | reports/optimization-batch-final-68f32db-20261006T172330Z-be405b.json | 85efe77602b4b33a2063b4cafff4163ec6d107f30018f92b65a0aa45d4dcb727 | 68f32db439f445b8f72faf92dc62fbc5b9dce738 | 68f32db439f445b8f72faf92dc62fbc5b9dce738 | VERIFIED_SEQUENCE_REFERENCE |
| fast | passed | reports/optimization-fast-final-68f32db-20261006T181339Z-74d92e.json | 6bf0e3060c136d4d167f137becf24f0630eef2d4f6e33b8db87027e235edd4bf | 68f32db439f445b8f72faf92dc62fbc5b9dce738 | 68f32db439f445b8f72faf92dc62fbc5b9dce738 | VERIFIED_SEQUENCE_REFERENCE |

### Conditions / baseline

```json
{
  "backpressure_hold_seconds": 120.0,
  "feed_period_seconds": 0.5,
  "hotspot_channels": 4,
  "hotspot_sinks": 4,
  "hotspot_sources": 4,
  "input_attempt_FE": 32000,
  "low_flow_probes_per_path_per_repeat": 40,
  "poll_seconds": 0.1,
  "probe_amount_FE": 1024,
  "probe_idle_seconds": 2.2,
  "repeats": 3,
  "resource": "cross_tesseract:fe",
  "scenarios": [
    "same",
    "cross",
    "mixed"
  ],
  "sink_pull_request_FE": 2147483647,
  "steady_seconds": 120.0,
  "warmup_seconds": 30.0,
  "workload": "Fixed ceil(seconds/feed_period) rounds; delayed rounds are retained and actual duration reported"
}
```

Configured feed rounds per source per steady window: 240. A 120 s / 0.5 s window has 240 rounds per source; total attempts depend on the actual fixture source count. Every repeat's planned and actual totals are retained below.

Explicit identity source evidence:

```json
{
  "other_children_hash_verification": "Only the selected profile child SHA is verified by this binding",
  "profile_input": {
    "bytes": 4421710,
    "path": "/workspace/reports/optimization-original-final-87bf217-20261006T145840Z-0d4630.json",
    "sha256": "35700d3cfff60022c381f38fab52a3d3daf745b842b1e29309a9cf68a1c5a676"
  },
  "raw_workspace_git_head": "75392af252744f240253d134d1da565a49b2cc9f",
  "referenced_child_paths": [
    "/workspace/reports/optimization-container-container-original2-87bf217-20261006T141818Z-8488a9.json",
    "/workspace/reports/optimization-original-pressure-87bf217-20261006T144116Z-38d872.json",
    "/workspace/reports/optimization-original-final-87bf217-20261006T145840Z-0d4630.json"
  ],
  "scope": "Operator-declared runtime revision from an explicitly supplied completed orchestrator, bound to the exact profile report by a unique path reference and SHA-256. This is not classloader attestation. The raw git_head remains the reported workspace checkout; functional/resource checks and profile status are unchanged.",
  "selected_run": {
    "command": [
      "python3",
      "scripts/optimization-benchmark.py",
      "--label",
      "original-final-87bf217",
      "--scenarios",
      "same,cross,mixed",
      "--warmup",
      "30",
      "--seconds",
      "120",
      "--repeats",
      "3",
      "--probes",
      "40"
    ],
    "exit_code": 0,
    "failures": [],
    "loaded_source_revision_declared": "87bf217fcaffcceb2629c36bb54d5158b9f461e8",
    "log": "logs/optimization-original-final-87bf217.log",
    "regressions": [],
    "report": "reports/optimization-original-final-87bf217-20261006T145840Z-0d4630.json",
    "report_sha256": "35700d3cfff60022c381f38fab52a3d3daf745b842b1e29309a9cf68a1c5a676",
    "utc_end": "2026-10-06T15:48:13Z",
    "utc_start": "2026-10-06T14:58:40Z"
  },
  "selected_run_index": 2,
  "sequence": {
    "bytes": 2967,
    "completion_policy": "legacy schema: passed=true and utc_end; procedure_completed absent",
    "metadata": {
      "loaded_source_revision_declared": "87bf217fcaffcceb2629c36bb54d5158b9f461e8",
      "observers": "Single RCON workload observer only; no concurrent RCON/tick/SQL/JFR sidecars. Current per-run scripts retain their own fixed monitoring reads.",
      "passed": true,
      "runs": [
        {
          "command": [
            "python3",
            "scripts/optimization-container-benchmark.py",
            "--label",
            "container-original2-87bf217",
            "--operator-revision",
            "87bf217fcaffcceb2629c36bb54d5158b9f461e8",
            "--scenarios",
            "same,cross,mixed",
            "--probes",
            "2",
            "--timeout",
            "420",
            "--idle",
            "2.2",
            "--poll",
            ".1",
            "--execute"
          ],
          "exit_code": 0,
          "failures": [],
          "loaded_source_revision_declared": "87bf217fcaffcceb2629c36bb54d5158b9f461e8",
          "log": "logs/optimization-container-original2-87bf217.log",
          "regressions": [],
          "report": "reports/optimization-container-container-original2-87bf217-20261006T141818Z-8488a9.json",
          "report_sha256": "212c6dc79e00989e48ae43e8d7b475d8fcbba780fc099ef91ea1f25dc2ce600a",
          "utc_end": "2026-10-06T14:41:16Z",
          "utc_start": "2026-10-06T14:18:18Z"
        },
        {
          "command": [
            "python3",
            "scripts/optimization-benchmark.py",
            "--label",
            "original-pressure-87bf217",
            "--scenarios",
            "backpressure,hotspot",
            "--warmup",
            "30",
            "--seconds",
            "120",
            "--repeats",
            "3",
            "--probes",
            "0"
          ],
          "exit_code": 0,
          "failures": [],
          "loaded_source_revision_declared": "87bf217fcaffcceb2629c36bb54d5158b9f461e8",
          "log": "logs/optimization-original-pressure-87bf217.log",
          "regressions": [],
          "report": "reports/optimization-original-pressure-87bf217-20261006T144116Z-38d872.json",
          "report_sha256": "2eef02f7cf00467abb7db371e137e8edc814ea900734362692af422a6cfd9f8e",
          "utc_end": "2026-10-06T14:58:07Z",
          "utc_start": "2026-10-06T14:41:16Z"
        },
        {
          "command": [
            "python3",
            "scripts/optimization-benchmark.py",
            "--label",
            "original-final-87bf217",
            "--scenarios",
            "same,cross,mixed",
            "--warmup",
            "30",
            "--seconds",
            "120",
            "--repeats",
            "3",
            "--probes",
            "40"
          ],
          "exit_code": 0,
          "failures": [],
          "loaded_source_revision_declared": "87bf217fcaffcceb2629c36bb54d5158b9f461e8",
          "log": "logs/optimization-original-final-87bf217.log",
          "regressions": [],
          "report": "reports/optimization-original-final-87bf217-20261006T145840Z-0d4630.json",
          "report_sha256": "35700d3cfff60022c381f38fab52a3d3daf745b842b1e29309a9cf68a1c5a676",
          "utc_end": "2026-10-06T15:48:13Z",
          "utc_start": "2026-10-06T14:58:40Z"
        }
      ],
      "stage": "original",
      "utc_end": "2026-10-06T15:48:17Z"
    },
    "path": "/workspace/reports/optimization-final-sequence-original.json",
    "sha256": "0c5be4798dccbdadc99becbf92d598a9fd19f6be0b2a87ba4385b6af90a66252"
  },
  "status": "VERIFIED_SEQUENCE_REFERENCE"
}
```

### Conditions / batch

```json
{
  "backpressure_hold_seconds": 120.0,
  "feed_period_seconds": 0.5,
  "hotspot_channels": 4,
  "hotspot_sinks": 4,
  "hotspot_sources": 4,
  "input_attempt_FE": 32000,
  "low_flow_probes_per_path_per_repeat": 40,
  "poll_seconds": 0.1,
  "probe_amount_FE": 1024,
  "probe_idle_seconds": 2.2,
  "repeats": 3,
  "resource": "cross_tesseract:fe",
  "scenarios": [
    "same",
    "cross",
    "mixed"
  ],
  "sink_pull_request_FE": 2147483647,
  "steady_seconds": 120.0,
  "warmup_seconds": 30.0,
  "workload": "Fixed ceil(seconds/feed_period) rounds; delayed rounds are retained and actual duration reported"
}
```

Configured feed rounds per source per steady window: 240. A 120 s / 0.5 s window has 240 rounds per source; total attempts depend on the actual fixture source count. Every repeat's planned and actual totals are retained below.

Explicit identity source evidence:

```json
{
  "other_children_hash_verification": "Only the selected profile child SHA is verified by this binding",
  "profile_input": {
    "bytes": 4553562,
    "path": "/workspace/reports/optimization-batch-final-68f32db-20261006T172330Z-be405b.json",
    "sha256": "85efe77602b4b33a2063b4cafff4163ec6d107f30018f92b65a0aa45d4dcb727"
  },
  "raw_workspace_git_head": "68f32db439f445b8f72faf92dc62fbc5b9dce738",
  "referenced_child_paths": [
    "/workspace/reports/optimization-container-container-current-68f32db-68f32db-20261006T170440Z-f3e5f6.json",
    "/workspace/reports/optimization-current-pressure-68f32db-20261006T170630Z-ae7dcd.json",
    "/workspace/reports/optimization-batch-final-68f32db-20261006T172330Z-be405b.json",
    "/workspace/reports/optimization-fast-final-68f32db-20261006T181339Z-74d92e.json"
  ],
  "scope": "Operator-declared runtime revision from an explicitly supplied completed orchestrator, bound to the exact profile report by a unique path reference and SHA-256. This is not classloader attestation. The raw git_head remains the reported workspace checkout; functional/resource checks and profile status are unchanged.",
  "selected_run": {
    "command": [
      "python3",
      "scripts/optimization-benchmark.py",
      "--label",
      "batch-final-68f32db",
      "--scenarios",
      "same,cross,mixed",
      "--warmup",
      "30",
      "--seconds",
      "120",
      "--repeats",
      "3",
      "--probes",
      "40",
      "--baseline",
      "reports/optimization-original-final-87bf217-20261006T145840Z-0d4630.json"
    ],
    "exit_code": 0,
    "failures": [],
    "loaded_source_revision_declared": "68f32db439f445b8f72faf92dc62fbc5b9dce738",
    "log": "logs/optimization-batch-final-68f32db.log",
    "regressions": [],
    "report": "reports/optimization-batch-final-68f32db-20261006T172330Z-be405b.json",
    "report_sha256": "85efe77602b4b33a2063b4cafff4163ec6d107f30018f92b65a0aa45d4dcb727",
    "utc_end": "2026-10-06T18:13:01Z",
    "utc_start": "2026-10-06T17:23:29Z"
  },
  "selected_run_index": 2,
  "sequence": {
    "bytes": 4519,
    "completion_policy": "explicit procedure_completed=true, passed=true and utc_end",
    "metadata": {
      "jar_sha256": "7924ab808667c69aabbbe71c2c92f1294437a7cc8bb19e409c366af1f682553a",
      "loaded_source_revision_declared": "68f32db439f445b8f72faf92dc62fbc5b9dce738",
      "observers": "Single RCON workload observer only; no concurrent RCON/tick/SQL/JFR sidecars. Current per-run scripts retain their own fixed monitoring reads.",
      "passed": true,
      "passed_definition": "All requested procedures and functional gates completed; performance regressions remain separately recorded in every run and are not erased.",
      "performance_regressions": [],
      "procedure_completed": true,
      "runs": [
        {
          "command": [
            "python3",
            "scripts/optimization-container-benchmark.py",
            "--label",
            "container-current-68f32db-68f32db",
            "--operator-revision",
            "68f32db439f445b8f72faf92dc62fbc5b9dce738",
            "--scenarios",
            "same,cross,mixed",
            "--probes",
            "2",
            "--timeout",
            "420",
            "--idle",
            "2.2",
            "--poll",
            ".1",
            "--execute"
          ],
          "exit_code": 0,
          "failures": [],
          "loaded_source_revision_declared": "68f32db439f445b8f72faf92dc62fbc5b9dce738",
          "log": "logs/optimization-container-current-68f32db-68f32db.log",
          "regressions": [],
          "report": "reports/optimization-container-container-current-68f32db-68f32db-20261006T170440Z-f3e5f6.json",
          "report_sha256": "c4d88f785dc49c0dace4b309b556015270a9a2438a1045c9a49c3e162777d585",
          "utc_end": "2026-10-06T17:06:30Z",
          "utc_start": "2026-10-06T17:04:40Z"
        },
        {
          "command": [
            "python3",
            "scripts/optimization-benchmark.py",
            "--label",
            "current-pressure-68f32db",
            "--scenarios",
            "backpressure,hotspot",
            "--warmup",
            "30",
            "--seconds",
            "120",
            "--repeats",
            "3",
            "--probes",
            "0",
            "--baseline",
            "reports/optimization-original-pressure-87bf217-20261006T144116Z-38d872.json"
          ],
          "exit_code": 0,
          "failures": [],
          "loaded_source_revision_declared": "68f32db439f445b8f72faf92dc62fbc5b9dce738",
          "log": "logs/optimization-current-pressure-68f32db.log",
          "regressions": [],
          "report": "reports/optimization-current-pressure-68f32db-20261006T170630Z-ae7dcd.json",
          "report_sha256": "f7b8c245e530d247744dc76c20a336fa364960d2130c30de33b3b88868fd1ef2",
          "utc_end": "2026-10-06T17:22:54Z",
          "utc_start": "2026-10-06T17:06:30Z"
        },
        {
          "command": [
            "python3",
            "scripts/optimization-benchmark.py",
            "--label",
            "batch-final-68f32db",
            "--scenarios",
            "same,cross,mixed",
            "--warmup",
            "30",
            "--seconds",
            "120",
            "--repeats",
            "3",
            "--probes",
            "40",
            "--baseline",
            "reports/optimization-original-final-87bf217-20261006T145840Z-0d4630.json"
          ],
          "exit_code": 0,
          "failures": [],
          "loaded_source_revision_declared": "68f32db439f445b8f72faf92dc62fbc5b9dce738",
          "log": "logs/optimization-batch-final-68f32db.log",
          "regressions": [],
          "report": "reports/optimization-batch-final-68f32db-20261006T172330Z-be405b.json",
          "report_sha256": "85efe77602b4b33a2063b4cafff4163ec6d107f30018f92b65a0aa45d4dcb727",
          "utc_end": "2026-10-06T18:13:01Z",
          "utc_start": "2026-10-06T17:23:29Z"
        },
        {
          "command": [
            "python3",
            "scripts/optimization-benchmark.py",
            "--label",
            "fast-final-68f32db",
            "--scenarios",
            "same,cross,mixed",
            "--warmup",
            "30",
            "--seconds",
            "120",
            "--repeats",
            "3",
            "--probes",
            "40",
            "--baseline",
            "reports/optimization-original-final-87bf217-20261006T145840Z-0d4630.json"
          ],
          "exit_code": 0,
          "failures": [],
          "loaded_source_revision_declared": "68f32db439f445b8f72faf92dc62fbc5b9dce738",
          "log": "logs/optimization-fast-final-68f32db.log",
          "regressions": [],
          "report": "reports/optimization-fast-final-68f32db-20261006T181339Z-74d92e.json",
          "report_sha256": "6bf0e3060c136d4d167f137becf24f0630eef2d4f6e33b8db87027e235edd4bf",
          "utc_end": "2026-10-06T18:51:42Z",
          "utc_start": "2026-10-06T18:13:39Z"
        }
      ],
      "source_manifest_sha256": "76ae7eca7b1f3a6df0a1d3ee80250ad5a4f7fd143ad2eb4aa008dc6ec8ec7577",
      "stage": "current",
      "utc_end": "2026-10-06T18:51:46Z"
    },
    "path": "/workspace/reports/optimization-final-sequence-current-68f32db.json",
    "sha256": "6cef499ebc0b9c2f40d65c39cc12b39e689f7d3ad387b51fa513438fa9a7b691"
  },
  "status": "VERIFIED_SEQUENCE_REFERENCE"
}
```

### Conditions / fast

```json
{
  "backpressure_hold_seconds": 120.0,
  "feed_period_seconds": 0.5,
  "hotspot_channels": 4,
  "hotspot_sinks": 4,
  "hotspot_sources": 4,
  "input_attempt_FE": 32000,
  "low_flow_probes_per_path_per_repeat": 40,
  "poll_seconds": 0.1,
  "probe_amount_FE": 1024,
  "probe_idle_seconds": 2.2,
  "repeats": 3,
  "resource": "cross_tesseract:fe",
  "scenarios": [
    "same",
    "cross",
    "mixed"
  ],
  "sink_pull_request_FE": 2147483647,
  "steady_seconds": 120.0,
  "warmup_seconds": 30.0,
  "workload": "Fixed ceil(seconds/feed_period) rounds; delayed rounds are retained and actual duration reported"
}
```

Configured feed rounds per source per steady window: 240. A 120 s / 0.5 s window has 240 rounds per source; total attempts depend on the actual fixture source count. Every repeat's planned and actual totals are retained below.

Explicit identity source evidence:

```json
{
  "other_children_hash_verification": "Only the selected profile child SHA is verified by this binding",
  "profile_input": {
    "bytes": 2523096,
    "path": "/workspace/reports/optimization-fast-final-68f32db-20261006T181339Z-74d92e.json",
    "sha256": "6bf0e3060c136d4d167f137becf24f0630eef2d4f6e33b8db87027e235edd4bf"
  },
  "raw_workspace_git_head": "68f32db439f445b8f72faf92dc62fbc5b9dce738",
  "referenced_child_paths": [
    "/workspace/reports/optimization-container-container-current-68f32db-68f32db-20261006T170440Z-f3e5f6.json",
    "/workspace/reports/optimization-current-pressure-68f32db-20261006T170630Z-ae7dcd.json",
    "/workspace/reports/optimization-batch-final-68f32db-20261006T172330Z-be405b.json",
    "/workspace/reports/optimization-fast-final-68f32db-20261006T181339Z-74d92e.json"
  ],
  "scope": "Operator-declared runtime revision from an explicitly supplied completed orchestrator, bound to the exact profile report by a unique path reference and SHA-256. This is not classloader attestation. The raw git_head remains the reported workspace checkout; functional/resource checks and profile status are unchanged.",
  "selected_run": {
    "command": [
      "python3",
      "scripts/optimization-benchmark.py",
      "--label",
      "fast-final-68f32db",
      "--scenarios",
      "same,cross,mixed",
      "--warmup",
      "30",
      "--seconds",
      "120",
      "--repeats",
      "3",
      "--probes",
      "40",
      "--baseline",
      "reports/optimization-original-final-87bf217-20261006T145840Z-0d4630.json"
    ],
    "exit_code": 0,
    "failures": [],
    "loaded_source_revision_declared": "68f32db439f445b8f72faf92dc62fbc5b9dce738",
    "log": "logs/optimization-fast-final-68f32db.log",
    "regressions": [],
    "report": "reports/optimization-fast-final-68f32db-20261006T181339Z-74d92e.json",
    "report_sha256": "6bf0e3060c136d4d167f137becf24f0630eef2d4f6e33b8db87027e235edd4bf",
    "utc_end": "2026-10-06T18:51:42Z",
    "utc_start": "2026-10-06T18:13:39Z"
  },
  "selected_run_index": 3,
  "sequence": {
    "bytes": 4519,
    "completion_policy": "explicit procedure_completed=true, passed=true and utc_end",
    "metadata": {
      "jar_sha256": "7924ab808667c69aabbbe71c2c92f1294437a7cc8bb19e409c366af1f682553a",
      "loaded_source_revision_declared": "68f32db439f445b8f72faf92dc62fbc5b9dce738",
      "observers": "Single RCON workload observer only; no concurrent RCON/tick/SQL/JFR sidecars. Current per-run scripts retain their own fixed monitoring reads.",
      "passed": true,
      "passed_definition": "All requested procedures and functional gates completed; performance regressions remain separately recorded in every run and are not erased.",
      "performance_regressions": [],
      "procedure_completed": true,
      "runs": [
        {
          "command": [
            "python3",
            "scripts/optimization-container-benchmark.py",
            "--label",
            "container-current-68f32db-68f32db",
            "--operator-revision",
            "68f32db439f445b8f72faf92dc62fbc5b9dce738",
            "--scenarios",
            "same,cross,mixed",
            "--probes",
            "2",
            "--timeout",
            "420",
            "--idle",
            "2.2",
            "--poll",
            ".1",
            "--execute"
          ],
          "exit_code": 0,
          "failures": [],
          "loaded_source_revision_declared": "68f32db439f445b8f72faf92dc62fbc5b9dce738",
          "log": "logs/optimization-container-current-68f32db-68f32db.log",
          "regressions": [],
          "report": "reports/optimization-container-container-current-68f32db-68f32db-20261006T170440Z-f3e5f6.json",
          "report_sha256": "c4d88f785dc49c0dace4b309b556015270a9a2438a1045c9a49c3e162777d585",
          "utc_end": "2026-10-06T17:06:30Z",
          "utc_start": "2026-10-06T17:04:40Z"
        },
        {
          "command": [
            "python3",
            "scripts/optimization-benchmark.py",
            "--label",
            "current-pressure-68f32db",
            "--scenarios",
            "backpressure,hotspot",
            "--warmup",
            "30",
            "--seconds",
            "120",
            "--repeats",
            "3",
            "--probes",
            "0",
            "--baseline",
            "reports/optimization-original-pressure-87bf217-20261006T144116Z-38d872.json"
          ],
          "exit_code": 0,
          "failures": [],
          "loaded_source_revision_declared": "68f32db439f445b8f72faf92dc62fbc5b9dce738",
          "log": "logs/optimization-current-pressure-68f32db.log",
          "regressions": [],
          "report": "reports/optimization-current-pressure-68f32db-20261006T170630Z-ae7dcd.json",
          "report_sha256": "f7b8c245e530d247744dc76c20a336fa364960d2130c30de33b3b88868fd1ef2",
          "utc_end": "2026-10-06T17:22:54Z",
          "utc_start": "2026-10-06T17:06:30Z"
        },
        {
          "command": [
            "python3",
            "scripts/optimization-benchmark.py",
            "--label",
            "batch-final-68f32db",
            "--scenarios",
            "same,cross,mixed",
            "--warmup",
            "30",
            "--seconds",
            "120",
            "--repeats",
            "3",
            "--probes",
            "40",
            "--baseline",
            "reports/optimization-original-final-87bf217-20261006T145840Z-0d4630.json"
          ],
          "exit_code": 0,
          "failures": [],
          "loaded_source_revision_declared": "68f32db439f445b8f72faf92dc62fbc5b9dce738",
          "log": "logs/optimization-batch-final-68f32db.log",
          "regressions": [],
          "report": "reports/optimization-batch-final-68f32db-20261006T172330Z-be405b.json",
          "report_sha256": "85efe77602b4b33a2063b4cafff4163ec6d107f30018f92b65a0aa45d4dcb727",
          "utc_end": "2026-10-06T18:13:01Z",
          "utc_start": "2026-10-06T17:23:29Z"
        },
        {
          "command": [
            "python3",
            "scripts/optimization-benchmark.py",
            "--label",
            "fast-final-68f32db",
            "--scenarios",
            "same,cross,mixed",
            "--warmup",
            "30",
            "--seconds",
            "120",
            "--repeats",
            "3",
            "--probes",
            "40",
            "--baseline",
            "reports/optimization-original-final-87bf217-20261006T145840Z-0d4630.json"
          ],
          "exit_code": 0,
          "failures": [],
          "loaded_source_revision_declared": "68f32db439f445b8f72faf92dc62fbc5b9dce738",
          "log": "logs/optimization-fast-final-68f32db.log",
          "regressions": [],
          "report": "reports/optimization-fast-final-68f32db-20261006T181339Z-74d92e.json",
          "report_sha256": "6bf0e3060c136d4d167f137becf24f0630eef2d4f6e33b8db87027e235edd4bf",
          "utc_end": "2026-10-06T18:51:42Z",
          "utc_start": "2026-10-06T18:13:39Z"
        }
      ],
      "source_manifest_sha256": "76ae7eca7b1f3a6df0a1d3ee80250ad5a4f7fd143ad2eb4aa008dc6ec8ec7577",
      "stage": "current",
      "utc_end": "2026-10-06T18:51:46Z"
    },
    "path": "/workspace/reports/optimization-final-sequence-current-68f32db.json",
    "sha256": "6cef499ebc0b9c2f40d65c39cc12b39e689f7d3ad387b51fa513438fa9a7b691"
  },
  "status": "VERIFIED_SEQUENCE_REFERENCE"
}
```

## Repeat-median main results

| Profile | Path | Case state | Complete/expected repeats | Full lower p50 / p95 / p99 ms | Full upper p50 / p95 / p99 ms | Actual attempts/window | SQL tx/window | Account statements/window | Steady accepted FE | Steady extracted FE | Steady extracted FE/s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | same | complete | 3/3 | 2827.952805 / 2940.634915 / 3028.46729 | 2829.638325 / 2942.988248 / 3030.499771 | 240 | 3440 | 33707 | 7680000 | 7488000 | 62399.9478232 |
| baseline | cross | complete | 3/3 | 2827.51539 / 2941.175239 / 2974.949059 | 2829.432542 / 2943.372719 / 2978.410654 | 240 | 3466 | 33517 | 7680000 | 7520000 | 62666.5428078 |
| baseline | mixed | complete | 3/3 | 2165.8268 / 3359.895157 / 3577.267603 | 2167.576405 / 3361.873106 / 3579.111712 | 240 | 3691 | 32560 | 7680000 | 7584000 | 63199.9427477 |
| batch | same | complete | 3/3 | 2223.356232 / 2327.165193 / 2328.872351 | 2225.251071 / 2329.118829 / 2330.681937 | 240 | 1953 | 22470 | 7680000 | 7520000 | 62666.6093894 |
| batch | cross | complete | 3/3 | 2225.138524 / 2330.019277 / 2424.081462 | 2226.89354 / 2332.044997 / 2425.665951 | 240 | 1913 | 21360 | 7680000 | 7520000 | 62666.5984755 |
| batch | mixed | complete | 3/3 | 2234.872794 / 2342.231267 / 2356.365761 | 2236.723916 / 2344.613303 / 2358.895169 | 240 | 2039 | 22997 | 7680000 | 7520000 | 62666.6167595 |
| fast | same | complete | 3/3 | 302.858057999 / 404.003559001 / 407.553716002 | 304.863192003 / 405.903973995 / 410.364926 | 240 | 2425 | 31788 | 7680000 | 7648000 | 63733.260516 |
| fast | cross | complete | 3/3 | 404.494859002 / 506.057916995 / 606.817213004 | 406.658720007 / 509.594960997 / 608.764842 | 240 | 3689 | 42545 | 7680000 | 7616000 | 63466.6154063 |
| fast | mixed | complete | 3/3 | 207.969561001 / 408.411313001 / 413.574870996 | 210.438335998 / 410.680841 / 417.713238996 | 240 | 3341 | 42672 | 7680000 | 7648000 | 63733.265434 |

| Profile | Path | Completed worker tasks / repeat median | Sql-helper statement attempts / repeat median | WAL writes / repeat median | WAL bytes / repeat median | Identical WAL skips / repeat median | Batch device appearances / repeat median | Batch record appearances / repeat median | Batch payload bytes / repeat median | Empty batches / repeat median | Total batch calls (only if explicitly measured) / repeat median |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | same | 641 | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED |
| baseline | cross | 638 | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED |
| baseline | mixed | 735 | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED |
| batch | same | 600 | 14834 | 622 | 156454 | 12 | 406 | 1200 | 0 | 287 | UNMEASURED |
| batch | cross | 606 | 13848 | 566 | 132389 | 14 | 380 | 1011 | 0 | 331 | UNMEASURED |
| batch | mixed | 748 | 14467 | 659 | 117691 | 12 | 543 | 962 | 0 | 276 | UNMEASURED |
| fast | same | 800 | 20822 | 1199 | 202728 | 0 | 800 | 1360 | 0 | 295 | UNMEASURED |
| fast | cross | 1405 | 27277 | 1404 | 252852 | 0 | 925 | 1672 | 0 | 534 | UNMEASURED |
| fast | mixed | 1417 | 26981 | 1438 | 229550 | 0 | 1297 | 1781 | 0 | 307 | UNMEASURED |

| Profile | Path | All-phase input event ledger FE | All-phase output event ledger FE | Latest cumulative accepted FE after drain | Latest cumulative extracted FE after drain | Latest checkpoint matches ledger |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | same | 28922880 | 28922880 | 28922880 | 28922880 | TRUE |
| baseline | cross | 28922880 | 28922880 | 28922880 | 28922880 | TRUE |
| baseline | mixed | 28922880 | 28922880 | 28922880 | 28922880 | TRUE |
| batch | same | 28922880 | 28922880 | 28922880 | 28922880 | TRUE |
| batch | cross | 28922880 | 28922880 | 28922880 | 28922880 | TRUE |
| batch | mixed | 28922880 | 28922880 | 28922880 | 28922880 | TRUE |
| fast | same | 28922880 | 28922880 | 28922880 | 28922880 | TRUE |
| fast | cross | 28922880 | 28922880 | 28922880 | 28922880 | TRUE |
| fast | mixed | 28922880 | 28922880 | 28922880 | 28922880 | TRUE |

Frozen goal context source (as supplied by aggregator):

```json
{
  "context": {
    "branch": "perf/channel-coordinator",
    "current_limits": {
      "FE_buffer": 2000000,
      "batch_ms": 200,
      "channel_endpoints": 256,
      "checks_per_tick": 16,
      "completion_queue": 256,
      "deposits_per_endpoint": 8,
      "main_budget_ms": 2,
      "quota_per_owner": 2,
      "worker_queue": 128,
      "workers": 3
    },
    "fixtures": {
      "cluster": "dev_three_v1",
      "existing_eula_records": [
        "/workspace/run-A/eula.txt",
        "/workspace/run-B/eula.txt",
        "/workspace/run-C/eula.txt"
      ],
      "optional_mods": [],
      "server_ids": [
        "opt-baseline-A",
        "opt-baseline-B",
        "opt-baseline-C"
      ],
      "worlds": [
        "world-opt-baseline-A",
        "world-opt-baseline-B",
        "world-opt-baseline-C"
      ]
    },
    "frozen_targets": {
      "cross_server_p95_max_regression_percent": 20,
      "fairness": "all eligible mixed receivers served; no added local priority",
      "idle_transactions_reduction_percent": 30,
      "integrity": "ownership, lifecycle, and queue safety regression tests must pass",
      "same_server_low_flow_p95_reduction_percent": 40,
      "transactions_per_fixed_external_workload_reduction_percent": 30
    },
    "head": "87bf217fcaffcceb2629c36bb54d5158b9f461e8",
    "initial_worktree_clean": true,
    "target_freeze_evidence": "10 persisted same-server low-flow probes at baseline HEAD 87bf217, observed upper intervals 2738-2841 ms; full baseline continues on immutable launch classes.",
    "utc": "2026-10-06T08:58:53.515379+00:00",
    "versions": {
      "gradle": "9.2.1",
      "java": "Temurin 21.0.8+9",
      "minecraft": "1.21.1",
      "mysql": "8.4.7",
      "neoforge": "21.1.252",
      "protocol": 1,
      "redis": "7.4.6",
      "resource_format": 1,
      "schema": "V001-V004",
      "wal_format": 2
    }
  },
  "path": "/workspace/reports/optimization-baseline-context.json",
  "sha256": "0d3c0117751db2978461cf833647be190ef328db2122b25403b9c9ab5e7c8856"
}
```

## Frozen performance goals

Goal outcomes below are copied exclusively from frozen_target_assessments. Functional passed status does not establish a performance goal. No goal is inferred when the assessment is absent or unmatched.

### baseline → batch

Recorded assessment status: MATCHED_DESCRIPTIVE_EVALUATION

Declared goals:

```json
{
  "cross_server_p95_max_regression_percent": 20,
  "fairness": "all eligible mixed receivers served; no added local priority",
  "idle_transactions_reduction_percent": 30,
  "integrity": "ownership, lifecycle, and queue safety regression tests must pass",
  "same_server_low_flow_p95_reduction_percent": 40,
  "transactions_per_fixed_external_workload_reduction_percent": 30
}
```

| Path | DB reduction goal % | Baseline median | Current median | Observed reduction % | Median goal | All paired repeat reductions % | All repeat goal |
| --- | --- | --- | --- | --- | --- | --- | --- |
| same | 30 | 3440 | 1953 | 43.226744186 | MET | {"1": 47.48588330196289, "2": 42.13138686131387, "3": 44.24418604651162} | MET |
| cross | 30 | 3466 | 1913 | 44.8066935949 | MET | {"1": 44.34532374100719, "2": 44.27614331488494, "3": 46.24927870744374} | MET |
| mixed | 30 | 3691 | 2039 | 44.7575182877 | MET | {"1": 40.401653868871826, "2": 44.7575182877269, "3": 44.986666666666665} | MET |

All three path medians meet DB goal: MET

| Frozen latency goal | Declared % | Observed change % | Recorded goal outcome |
| --- | --- | --- | --- |
| same_server_low_flow_p95_reduction_percent | 40 | -20.8587111897 | NOT MET |
| cross_server_p95_max_regression_percent | 20 | -20.7696333548 | MET |

Idle: UNMEASURED by this FE driver; separate loaded-endpoint OFF measurement required

Integrity scope: Native recovery/lifecycle/fault tests are separate evidence, not established by this FE latency report alone

Assessment scope: Successful database transaction count per identical fixed external workload, individually for same/cross/mixed. Repeat-median changes and all paired repeats retained; worker task count is separate. No restriction of the original generic workload goal to same-server cases.

### baseline → fast

Recorded assessment status: MATCHED_DESCRIPTIVE_EVALUATION

Declared goals:

```json
{
  "cross_server_p95_max_regression_percent": 20,
  "fairness": "all eligible mixed receivers served; no added local priority",
  "idle_transactions_reduction_percent": 30,
  "integrity": "ownership, lifecycle, and queue safety regression tests must pass",
  "same_server_low_flow_p95_reduction_percent": 40,
  "transactions_per_fixed_external_workload_reduction_percent": 30
}
```

| Path | DB reduction goal % | Baseline median | Current median | Observed reduction % | Median goal | All paired repeat reductions % | All repeat goal |
| --- | --- | --- | --- | --- | --- | --- | --- |
| same | 30 | 3440 | 2425 | 29.5058139535 | NOT MET | {"1": 35.00941113202474, "2": 28.583941605839414, "3": 29.50581395348837} | NOT MET |
| cross | 30 | 3466 | 3689 | -6.43392960185 | NOT MET | {"1": -6.158273381294954, "2": -3.262452665307314, "3": -7.328332371609925} | NOT MET |
| mixed | 30 | 3691 | 3341 | 9.48252506096 | NOT MET | {"1": 4.016538688718252, "2": 9.482525060959091, "3": 10.773333333333335} | NOT MET |

All three path medians meet DB goal: NOT MET

| Frozen latency goal | Declared % | Observed change % | Recorded goal outcome |
| --- | --- | --- | --- |
| same_server_low_flow_p95_reduction_percent | 40 | -86.207760963 | MET |
| cross_server_p95_max_regression_percent | 20 | -82.686699591 | MET |

Idle: UNMEASURED by this FE driver; separate loaded-endpoint OFF measurement required

Integrity scope: Native recovery/lifecycle/fault tests are separate evidence, not established by this FE latency report alone

Assessment scope: Successful database transaction count per identical fixed external workload, individually for same/cross/mixed. Repeat-median changes and all paired repeats retained; worker task count is separate. No restriction of the original generic workload goal to same-server cases.

## All recorded repeats, costs, recipient service and drain

### baseline / same

Case status: complete; missing/incomplete repeats: []; duplicate repeat IDs: FALSE

Recorded topology:

```json
{
  "IO": "Source receiveEnergy -> sink extractEnergy through ct_test; no real chest/machine evidence",
  "dimensions": [
    "minecraft:overworld (ct_test fixture contract)"
  ],
  "lanes": [
    {
      "name": "same",
      "sinks": [
        "A"
      ],
      "sources": [
        "A"
      ]
    }
  ],
  "neighbor_note": "NeighborPump skips adjacent TesseractBlockEntity; adjacency is not a direct neighbor transfer",
  "per_server_chunk_counts": {
    "A": 1
  }
}
```

| Repeat | Reported pass | Recorded complete | Planned attempts | Actual attempts | Steady accepted FE | Steady extracted FE | Steady extracted FE/s | Steady tail to drain FE | SQL tx before final drain | Account statements before final drain |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | TRUE | TRUE | 240 | 240 | 7680000 | 7552000 | 62933.1846054 | 128000 | 3719 | 36061 |
| 2 | TRUE | TRUE | 240 | 240 | 7680000 | 7488000 | 62399.9478232 | 192000 | 3425 | 33489 |
| 3 | TRUE | TRUE | 240 | 240 | 7680000 | 7488000 | 62399.9402266 | 192000 | 3440 | 33707 |

| Repeat | Probes | Full-output lower p50 / p95 / p99 ms | Full-output upper p50 / p95 / p99 ms |
| --- | --- | --- | --- |
| 1 | 40 | 2741.797974 / 2940.634915 / 2944.980951 | 2744.427832 / 2942.988248 / 2948.061414 |
| 2 | 40 | 2829.939086 / 2935.373061 / 3042.384768 | 2831.789764 / 2937.24347 / 3044.245181 |
| 3 | 40 | 2827.952805 / 2952.0551 / 3028.46729 | 2829.638325 / 2954.390206 / 3030.499771 |

| Repeat | SQL transactions | Completed worker tasks | Sql-helper statement attempts | WAL writes | WAL bytes | Identical WAL skips | Batch device appearances | Batch record appearances | Batch payload bytes | Empty batches | Total batch calls (only if explicitly measured) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 3719 | 685 | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED |
| 2 | 3425 | 632 | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED |
| 3 | 3440 | 641 | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED |

| Repeat | Worker errors | Queue rejected | Quarantined | Deadlock retries | Account statement errors | All steady recipients served | Sink Jain index | Max sink pull gap s | Failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0 | 0 | 0 | 0 | 0 | TRUE | 1 | 2.001981459 | No recorded failure |
| 2 | 0 | 0 | 0 | 0 | 0 | TRUE | 1 | 3.001677708 | No recorded failure |
| 3 | 0 | 0 | 0 | 0 | 0 | TRUE | 1 | 3.002051244 | No recorded failure |

#### Recorded repeat 1

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| same_sink_0 | A | 7552000 | 1 | 236 | 2.001981459 | 119.502828522 | 2.001981459 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960,
  "residue": {
    "local_buffers": {
      "same_sink_0": {
        "channel": "80bd793f-d85f-41c2-b2ad-f4ba53027cc4",
        "checkpoint": 979,
        "id": "8f542264-af56-49c7-93fb-f4be29c4edf5",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "same_source_0": {
        "channel": "80bd793f-d85f-41c2-b2ad-f4ba53027cc4",
        "checkpoint": 1012,
        "id": "97dbf60c-1d5e-4731-be66-91fb305e8f84",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 1.1630161110006156
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [222.07534743699944, 222.0766832920017] | [342.1683213659999, 342.1713037119989] |
| B | [222.07674034799857, 222.0787221520004] | [342.1713801369988, 342.17654051299905] |
| C | [222.07877862700116, 222.08484687999953] | [342.17658899600065, 342.1786390929992] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          342.1683213659999,
          342.1713037119989
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          222.07534743699944,
          222.0766832920017
        ]
      }
    },
    "B": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          342.1713801369988,
          342.17654051299905
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          222.07674034799857,
          222.0787221520004
        ]
      }
    },
    "C": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          342.17658899600065,
          342.1786390929992
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          222.07877862700116,
          222.08484687999953
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

#### Recorded repeat 2

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| same_sink_0 | A | 7488000 | 1 | 234 | 3.001677708 | 119.501410215 | 3.001677708 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 19281920,
  "extracted_FE": 19281920,
  "residue": {
    "local_buffers": {
      "same_sink_0": {
        "channel": "80bd793f-d85f-41c2-b2ad-f4ba53027cc4",
        "checkpoint": 1868,
        "id": "8f542264-af56-49c7-93fb-f4be29c4edf5",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "same_source_0": {
        "channel": "80bd793f-d85f-41c2-b2ad-f4ba53027cc4",
        "checkpoint": 2026,
        "id": "97dbf60c-1d5e-4731-be66-91fb305e8f84",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 0.9853687140021066
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [1861.4451187880004, 1861.4462005720015] | [1981.518527070999, 1981.5205288760008] |
| B | [1861.446240551999, 1861.447825602001] | [1981.5206318109995, 1981.5223596340002] |
| C | [1861.447931220002, 1861.449208768001] | [1981.522404981999, 1981.5267135989998] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          1981.518527070999,
          1981.5205288760008
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          1861.4451187880004,
          1861.4462005720015
        ]
      }
    },
    "B": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          1981.5206318109995,
          1981.5223596340002
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          1861.446240551999,
          1861.447825602001
        ]
      }
    },
    "C": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          1981.522404981999,
          1981.5267135989998
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          1861.447931220002,
          1861.449208768001
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

#### Recorded repeat 3

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| same_sink_0 | A | 7488000 | 1 | 234 | 3.002051244 | 119.50143244 | 3.002051244 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 28922880,
  "extracted_FE": 28922880,
  "residue": {
    "local_buffers": {
      "same_sink_0": {
        "channel": "80bd793f-d85f-41c2-b2ad-f4ba53027cc4",
        "checkpoint": 2752,
        "id": "8f542264-af56-49c7-93fb-f4be29c4edf5",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "same_source_0": {
        "channel": "80bd793f-d85f-41c2-b2ad-f4ba53027cc4",
        "checkpoint": 3036,
        "id": "97dbf60c-1d5e-4731-be66-91fb305e8f84",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 0.9762224570004037
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [2521.404878240999, 2521.4058015260016] | [2641.4889858040005, 2641.4904255740003] |
| B | [2521.405849789, 2521.406998022001] | [2641.490487547002, 2641.491462831] |
| C | [2521.4070570309996, 2521.4086376429987] | [2641.491495339, 2641.493396441001] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          2641.4889858040005,
          2641.4904255740003
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          2521.404878240999,
          2521.4058015260016
        ]
      }
    },
    "B": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          2641.490487547002,
          2641.491462831
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          2521.405849789,
          2521.406998022001
        ]
      }
    },
    "C": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          2641.491495339,
          2641.493396441001
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          2521.4070570309996,
          2521.4086376429987
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

Recorded per-case error totals (missing measurements remain missing):

```json
{
  "low_flow": {
    "SQL_statement_errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "db_deadlock_retries": {
      "measured_samples": 3,
      "sum": 0
    },
    "errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "quarantined": {
      "measured_samples": 3,
      "sum": 0
    },
    "queue_rejected": {
      "measured_samples": 3,
      "sum": 0
    }
  },
  "steady": {
    "SQL_statement_errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "db_deadlock_retries": {
      "measured_samples": 3,
      "sum": 0
    },
    "errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "quarantined": {
      "measured_samples": 3,
      "sum": 0
    },
    "queue_rejected": {
      "measured_samples": 3,
      "sum": 0
    }
  }
}
```

Final case conservation summary (latest cumulative figures, never sum repeated checkpoints):

```json
{
  "all_phase_event_ledger": {
    "accepted_FE": 28922880,
    "extracted_FE": 28922880
  },
  "do_not_sum_repeats": "Conservation values are cumulative per reused channel, not independent repeat totals.",
  "latest_cumulative_accepted_FE": 28922880,
  "latest_cumulative_extracted_FE": 28922880,
  "latest_cumulative_matches_event_ledger": true
}
```

### baseline / cross

Case status: complete; missing/incomplete repeats: []; duplicate repeat IDs: FALSE

Recorded topology:

```json
{
  "IO": "Source receiveEnergy -> sink extractEnergy through ct_test; no real chest/machine evidence",
  "dimensions": [
    "minecraft:overworld (ct_test fixture contract)"
  ],
  "lanes": [
    {
      "name": "cross",
      "sinks": [
        "B"
      ],
      "sources": [
        "A"
      ]
    }
  ],
  "neighbor_note": "NeighborPump skips adjacent TesseractBlockEntity; adjacency is not a direct neighbor transfer",
  "per_server_chunk_counts": {
    "A": 1,
    "B": 1
  }
}
```

| Repeat | Reported pass | Recorded complete | Planned attempts | Actual attempts | Steady accepted FE | Steady extracted FE | Steady extracted FE/s | Steady tail to drain FE | SQL tx before final drain | Account statements before final drain |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | TRUE | TRUE | 240 | 240 | 7680000 | 7520000 | 62666.5428078 | 160000 | 3475 | 33517 |
| 2 | TRUE | TRUE | 240 | 240 | 7680000 | 7488000 | 62399.9534897 | 192000 | 3433 | 33519 |
| 3 | TRUE | TRUE | 240 | 240 | 7680000 | 7584000 | 63199.9710813 | 96000 | 3466 | 31700 |

| Repeat | Probes | Full-output lower p50 / p95 / p99 ms | Full-output upper p50 / p95 / p99 ms |
| --- | --- | --- | --- |
| 1 | 40 | 2755.543438 / 2864.082436 / 2974.949059 | 2757.881628 / 2866.95032 / 2978.410654 |
| 2 | 40 | 2831.541186 / 2941.503085 / 2951.588668 | 2833.625756 / 2944.029082 / 2953.306386 |
| 3 | 40 | 2827.51539 / 2941.175239 / 3033.389321 | 2829.432542 / 2943.372719 / 3035.189209 |

| Repeat | SQL transactions | Completed worker tasks | Sql-helper statement attempts | WAL writes | WAL bytes | Identical WAL skips | Batch device appearances | Batch record appearances | Batch payload bytes | Empty batches | Total batch calls (only if explicitly measured) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 3475 | 638 | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED |
| 2 | 3433 | 632 | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED |
| 3 | 3466 | 642 | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED |

| Repeat | Worker errors | Queue rejected | Quarantined | Deadlock retries | Account statement errors | All steady recipients served | Sink Jain index | Max sink pull gap s | Failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0 | 0 | 0 | 0 | 0 | TRUE | 1 | 2.50483907 | No recorded failure |
| 2 | 0 | 0 | 0 | 0 | 0 | TRUE | 1 | 3.002014213 | No recorded failure |
| 3 | 0 | 0 | 0 | 0 | 0 | TRUE | 1 | 1.000325286 | No recorded failure |

#### Recorded repeat 1

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cross_sink_0 | B | 7520000 | 1 | 235 | 2.50483907 | 119.502829612 | 2.50483907 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960,
  "residue": {
    "local_buffers": {
      "cross_sink_0": {
        "channel": "e713af23-75af-4b04-b49e-a45d591d62d6",
        "checkpoint": 914,
        "id": "0abb39d2-8ec9-41d4-8e5a-8406d324be14",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "cross_source_0": {
        "channel": "e713af23-75af-4b04-b49e-a45d591d62d6",
        "checkpoint": 1008,
        "id": "72e377d2-91d2-41e3-b2b4-aa08fff0017c",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 0.851208564999979
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [554.0135159970014, 554.0161020670021] | [674.1328597290012, 674.135132751002] |
| B | [554.0161774699991, 554.0176581209998] | [674.1354100169992, 674.1381979610014] |
| C | [554.0177041899988, 554.0211566399994] | [674.1382500600012, 674.142127739] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          674.1328597290012,
          674.135132751002
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          554.0135159970014,
          554.0161020670021
        ]
      }
    },
    "B": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          674.1354100169992,
          674.1381979610014
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          554.0161774699991,
          554.0176581209998
        ]
      }
    },
    "C": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          674.1382500600012,
          674.142127739
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          554.0177041899988,
          554.0211566399994
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

#### Recorded repeat 2

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cross_sink_0 | B | 7488000 | 1 | 234 | 3.002014213 | 119.501629499 | 3.002014213 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 19281920,
  "extracted_FE": 19281920,
  "residue": {
    "local_buffers": {
      "cross_sink_0": {
        "channel": "e713af23-75af-4b04-b49e-a45d591d62d6",
        "checkpoint": 1787,
        "id": "0abb39d2-8ec9-41d4-8e5a-8406d324be14",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "cross_source_0": {
        "channel": "e713af23-75af-4b04-b49e-a45d591d62d6",
        "checkpoint": 2016,
        "id": "72e377d2-91d2-41e3-b2b4-aa08fff0017c",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 0.7649142840018612
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [1200.2218713399998, 1200.2236925430007] | [1320.3040697069991, 1320.3056162989997] |
| B | [1200.2237696590018, 1200.2251168610019] | [1320.3057019270018, 1320.3070454840017] |
| C | [1200.2251714429985, 1200.2273567230004] | [1320.3071064460019, 1320.3087034829987] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          1320.3040697069991,
          1320.3056162989997
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          1200.2218713399998,
          1200.2236925430007
        ]
      }
    },
    "B": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          1320.3057019270018,
          1320.3070454840017
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          1200.2237696590018,
          1200.2251168610019
        ]
      }
    },
    "C": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          1320.3071064460019,
          1320.3087034829987
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          1200.2251714429985,
          1200.2273567230004
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

#### Recorded repeat 3

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cross_sink_0 | B | 7584000 | 1 | 237 | 0.501537179 | 119.502985466 | 1.000325286 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 28922880,
  "extracted_FE": 28922880,
  "residue": {
    "local_buffers": {
      "cross_sink_0": {
        "channel": "e713af23-75af-4b04-b49e-a45d591d62d6",
        "checkpoint": 2674,
        "id": "0abb39d2-8ec9-41d4-8e5a-8406d324be14",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "cross_source_0": {
        "channel": "e713af23-75af-4b04-b49e-a45d591d62d6",
        "checkpoint": 3034,
        "id": "72e377d2-91d2-41e3-b2b4-aa08fff0017c",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 0.48086460800186615
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [2851.669367693001, 2851.67039784] | [2971.7552357329987, 2971.756477376999] |
| B | [2851.6704374190012, 2851.671270769999] | [2971.7565418839986, 2971.757584949999] |
| C | [2851.6713029790008, 2851.6725760100016] | [2971.757622134999, 2971.7589768290018] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          2971.7552357329987,
          2971.756477376999
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          2851.669367693001,
          2851.67039784
        ]
      }
    },
    "B": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          2971.7565418839986,
          2971.757584949999
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          2851.6704374190012,
          2851.671270769999
        ]
      }
    },
    "C": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          2971.757622134999,
          2971.7589768290018
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          2851.6713029790008,
          2851.6725760100016
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

Recorded per-case error totals (missing measurements remain missing):

```json
{
  "low_flow": {
    "SQL_statement_errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "db_deadlock_retries": {
      "measured_samples": 3,
      "sum": 0
    },
    "errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "quarantined": {
      "measured_samples": 3,
      "sum": 0
    },
    "queue_rejected": {
      "measured_samples": 3,
      "sum": 0
    }
  },
  "steady": {
    "SQL_statement_errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "db_deadlock_retries": {
      "measured_samples": 3,
      "sum": 0
    },
    "errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "quarantined": {
      "measured_samples": 3,
      "sum": 0
    },
    "queue_rejected": {
      "measured_samples": 3,
      "sum": 0
    }
  }
}
```

Final case conservation summary (latest cumulative figures, never sum repeated checkpoints):

```json
{
  "all_phase_event_ledger": {
    "accepted_FE": 28922880,
    "extracted_FE": 28922880
  },
  "do_not_sum_repeats": "Conservation values are cumulative per reused channel, not independent repeat totals.",
  "latest_cumulative_accepted_FE": 28922880,
  "latest_cumulative_extracted_FE": 28922880,
  "latest_cumulative_matches_event_ledger": true
}
```

### baseline / mixed

Case status: complete; missing/incomplete repeats: []; duplicate repeat IDs: FALSE

Recorded topology:

```json
{
  "IO": "Source receiveEnergy -> sink extractEnergy through ct_test; no real chest/machine evidence",
  "dimensions": [
    "minecraft:overworld (ct_test fixture contract)"
  ],
  "lanes": [
    {
      "name": "mixed",
      "sinks": [
        "A",
        "B"
      ],
      "sources": [
        "A"
      ]
    }
  ],
  "neighbor_note": "NeighborPump skips adjacent TesseractBlockEntity; adjacency is not a direct neighbor transfer",
  "per_server_chunk_counts": {
    "A": 1,
    "B": 1
  }
}
```

| Repeat | Reported pass | Recorded complete | Planned attempts | Actual attempts | Steady accepted FE | Steady extracted FE | Steady extracted FE/s | Steady tail to drain FE | SQL tx before final drain | Account statements before final drain |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | TRUE | TRUE | 240 | 240 | 7680000 | 7552000 | 62933.2806042 | 128000 | 3386 | 29601 |
| 2 | TRUE | TRUE | 240 | 240 | 7680000 | 7616000 | 63466.6229979 | 64000 | 3691 | 32560 |
| 3 | TRUE | TRUE | 240 | 240 | 7680000 | 7584000 | 63199.9427477 | 96000 | 3750 | 33120 |

| Repeat | Probes | Full-output lower p50 / p95 / p99 ms | Full-output upper p50 / p95 / p99 ms |
| --- | --- | --- | --- |
| 1 | 40 | 1839.332961 / 3376.798979 / 3577.267603 | 1841.243674 / 3381.655517 / 3579.111712 |
| 2 | 40 | 2655.985533 / 3076.356893 / 3164.647091 | 2657.685865 / 3078.320871 / 3166.435205 |
| 3 | 40 | 2165.8268 / 3359.895157 / 3770.547826 | 2167.576405 / 3361.873106 / 3772.535375 |

| Repeat | SQL transactions | Completed worker tasks | Sql-helper statement attempts | WAL writes | WAL bytes | Identical WAL skips | Batch device appearances | Batch record appearances | Batch payload bytes | Empty batches | Total batch calls (only if explicitly measured) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 3386 | 678 | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED |
| 2 | 3691 | 735 | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED |
| 3 | 3750 | 744 | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED |

| Repeat | Worker errors | Queue rejected | Quarantined | Deadlock retries | Account statement errors | All steady recipients served | Sink Jain index | Max sink pull gap s | Failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0 | 0 | 0 | 0 | 0 | TRUE | 0.998852223816 | 3.500477582 | No recorded failure |
| 2 | 0 | 0 | 0 | 0 | 0 | TRUE | 0.99823769914 | 5.002152868 | No recorded failure |
| 3 | 0 | 0 | 0 | 0 | 0 | TRUE | 0.999982196902 | 4.501817197 | No recorded failure |

#### Recorded repeat 1

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| mixed_sink_0 | A | 3648000 | 0.483050847458 | 114 | 1.506009971 | 118.001881806 | 3.497724708 |
| mixed_sink_1 | B | 3904000 | 0.516949152542 | 122 | 1.002402856 | 119.501809164 | 3.500477582 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960,
  "residue": {
    "local_buffers": {
      "mixed_sink_0": {
        "channel": "43501743-7cb8-4802-82de-b16d71ffbec8",
        "checkpoint": 341,
        "id": "c6db988c-95d0-42b7-9bc8-cdfcf7316e59",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "mixed_sink_1": {
        "channel": "43501743-7cb8-4802-82de-b16d71ffbec8",
        "checkpoint": 351,
        "id": "0fd152c6-386e-449d-95a9-4a7f935d5d00",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "mixed_source_0": {
        "channel": "43501743-7cb8-4802-82de-b16d71ffbec8",
        "checkpoint": 1016,
        "id": "48591783-284b-4e48-8982-4442c8d86a7e",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 1.7481023449981876
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [869.9367092110006, 869.9381373050019] | [990.0174857330021, 990.0190489150009] |
| B | [869.9381752219997, 869.9440931839999] | [990.0191092950008, 990.0210934140014] |
| C | [869.944136959999, 869.9488069399995] | [990.0211333939988, 990.0228957389991] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          990.0174857330021,
          990.0190489150009
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          869.9367092110006,
          869.9381373050019
        ]
      }
    },
    "B": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          990.0191092950008,
          990.0210934140014
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          869.9381752219997,
          869.9440931839999
        ]
      }
    },
    "C": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          990.0211333939988,
          990.0228957389991
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          869.944136959999,
          869.9488069399995
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

#### Recorded repeat 2

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| mixed_sink_0 | A | 3648000 | 0.478991596639 | 114 | 2.502492011 | 119.503406118 | 2.999909182 |
| mixed_sink_1 | B | 3968000 | 0.521008403361 | 124 | 5.002152868 | 119.00228066 | 5.002152868 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 19281920,
  "extracted_FE": 19281920,
  "residue": {
    "local_buffers": {
      "mixed_sink_0": {
        "channel": "43501743-7cb8-4802-82de-b16d71ffbec8",
        "checkpoint": 700,
        "id": "c6db988c-95d0-42b7-9bc8-cdfcf7316e59",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "mixed_sink_1": {
        "channel": "43501743-7cb8-4802-82de-b16d71ffbec8",
        "checkpoint": 722,
        "id": "0fd152c6-386e-449d-95a9-4a7f935d5d00",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "mixed_source_0": {
        "channel": "43501743-7cb8-4802-82de-b16d71ffbec8",
        "checkpoint": 2030,
        "id": "48591783-284b-4e48-8982-4442c8d86a7e",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 0.7366145739979402
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [1532.5452148330005, 1532.5463112079997] | [1652.6271346659996, 1652.629434499002] |
| B | [1532.546350257002, 1532.5476505789993] | [1652.6294977139987, 1652.6322049480004] |
| C | [1532.547682757002, 1532.549968358002] | [1652.6322683229992, 1652.6371161819989] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          1652.6271346659996,
          1652.629434499002
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          1532.5452148330005,
          1532.5463112079997
        ]
      }
    },
    "B": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          1652.6294977139987,
          1652.6322049480004
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          1532.546350257002,
          1532.5476505789993
        ]
      }
    },
    "C": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          1652.6322683229992,
          1652.6371161819989
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          1532.547682757002,
          1532.549968358002
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

#### Recorded repeat 3

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| mixed_sink_0 | A | 3776000 | 0.497890295359 | 118 | 4.501817197 | 118.00150225 | 4.501817197 |
| mixed_sink_1 | B | 3808000 | 0.502109704641 | 119 | 3.501527459 | 119.501723433 | 3.501527459 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 28922880,
  "extracted_FE": 28922880,
  "residue": {
    "local_buffers": {
      "mixed_sink_0": {
        "channel": "43501743-7cb8-4802-82de-b16d71ffbec8",
        "checkpoint": 1076,
        "id": "c6db988c-95d0-42b7-9bc8-cdfcf7316e59",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "mixed_sink_1": {
        "channel": "43501743-7cb8-4802-82de-b16d71ffbec8",
        "checkpoint": 1098,
        "id": "0fd152c6-386e-449d-95a9-4a7f935d5d00",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "mixed_source_0": {
        "channel": "43501743-7cb8-4802-82de-b16d71ffbec8",
        "checkpoint": 3040,
        "id": "48591783-284b-4e48-8982-4442c8d86a7e",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 0.38594060399918817
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [2191.121069959001, 2191.122187195] | [2311.205614814, 2311.207345341001] |
| B | [2191.1222391730007, 2191.1236903220015] | [2311.207427043999, 2311.2086070250007] |
| C | [2191.123757032001, 2191.1251639740003] | [2311.2086857130016, 2311.211098134001] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          2311.205614814,
          2311.207345341001
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          2191.121069959001,
          2191.122187195
        ]
      }
    },
    "B": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          2311.207427043999,
          2311.2086070250007
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          2191.1222391730007,
          2191.1236903220015
        ]
      }
    },
    "C": {
      "end": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          2311.2086857130016,
          2311.211098134001
        ]
      },
      "start": {
        "p50": null,
        "p95": null,
        "p99": null,
        "samples": null,
        "status": "UNMEASURED",
        "status_run_relative_interval": [
          2191.123757032001,
          2191.1251639740003
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

Recorded per-case error totals (missing measurements remain missing):

```json
{
  "low_flow": {
    "SQL_statement_errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "db_deadlock_retries": {
      "measured_samples": 3,
      "sum": 0
    },
    "errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "quarantined": {
      "measured_samples": 3,
      "sum": 0
    },
    "queue_rejected": {
      "measured_samples": 3,
      "sum": 0
    }
  },
  "steady": {
    "SQL_statement_errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "db_deadlock_retries": {
      "measured_samples": 3,
      "sum": 0
    },
    "errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "quarantined": {
      "measured_samples": 3,
      "sum": 0
    },
    "queue_rejected": {
      "measured_samples": 3,
      "sum": 0
    }
  }
}
```

Final case conservation summary (latest cumulative figures, never sum repeated checkpoints):

```json
{
  "all_phase_event_ledger": {
    "accepted_FE": 28922880,
    "extracted_FE": 28922880
  },
  "do_not_sum_repeats": "Conservation values are cumulative per reused channel, not independent repeat totals.",
  "latest_cumulative_accepted_FE": 28922880,
  "latest_cumulative_extracted_FE": 28922880,
  "latest_cumulative_matches_event_ledger": true
}
```

### batch / same

Case status: complete; missing/incomplete repeats: []; duplicate repeat IDs: FALSE

Recorded topology:

```json
{
  "IO": "Source receiveEnergy -> sink extractEnergy through ct_test; no real chest/machine evidence",
  "dimensions": [
    "minecraft:overworld (ct_test fixture contract)"
  ],
  "lanes": [
    {
      "name": "same",
      "sinks": [
        "A"
      ],
      "sources": [
        "A"
      ]
    }
  ],
  "neighbor_note": "NeighborPump skips adjacent TesseractBlockEntity; adjacency is not a direct neighbor transfer",
  "per_server_chunk_counts": {
    "A": 1
  }
}
```

| Repeat | Reported pass | Recorded complete | Planned attempts | Actual attempts | Steady accepted FE | Steady extracted FE | Steady extracted FE/s | Steady tail to drain FE | SQL tx before final drain | Account statements before final drain |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | TRUE | TRUE | 240 | 240 | 7680000 | 7520000 | 62666.6115456 | 160000 | 1953 | 21666 |
| 2 | TRUE | TRUE | 240 | 240 | 7680000 | 7520000 | 62666.6079783 | 160000 | 1982 | 23388 |
| 3 | TRUE | TRUE | 240 | 240 | 7680000 | 7520000 | 62666.6093894 | 160000 | 1918 | 22470 |

| Repeat | Probes | Full-output lower p50 / p95 / p99 ms | Full-output upper p50 / p95 / p99 ms |
| --- | --- | --- | --- |
| 1 | 40 | 2228.111542 / 2329.633153 / 2335.349308 | 2230.708884 / 2332.07805 / 2340.57826 |
| 2 | 40 | 2223.356232 / 2327.165193 / 2328.872351 | 2225.251071 / 2329.118829 / 2330.681937 |
| 3 | 40 | 2221.193507 / 2323.655229 / 2323.906717 | 2222.82234301 / 2325.686841 / 2326.93613999 |

| Repeat | SQL transactions | Completed worker tasks | Sql-helper statement attempts | WAL writes | WAL bytes | Identical WAL skips | Batch device appearances | Batch record appearances | Batch payload bytes | Empty batches | Total batch calls (only if explicitly measured) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1953 | 622 | 13952 | 579 | 129003 | 9 | 406 | 1014 | 0 | 287 | UNMEASURED |
| 2 | 1982 | 600 | 15434 | 634 | 162794 | 22 | 421 | 1280 | 0 | 275 | UNMEASURED |
| 3 | 1918 | 574 | 14834 | 622 | 156454 | 12 | 404 | 1200 | 0 | 308 | UNMEASURED |

| Repeat | Worker errors | Queue rejected | Quarantined | Deadlock retries | Account statement errors | All steady recipients served | Sink Jain index | Max sink pull gap s | Failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0 | 0 | 0 | 0 | 0 | TRUE | 1 | 2.005556083 | No recorded failure |
| 2 | 0 | 0 | 0 | 0 | 0 | TRUE | 1 | 2.00173246999 | No recorded failure |
| 3 | 0 | 0 | 0 | 0 | 0 | TRUE | 1 | 2.001542658 | No recorded failure |

#### Recorded repeat 1

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| same_sink_0 | A | 7520000 | 1 | 235 | 2.005556083 | 119.501910763 | 2.005556083 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960,
  "residue": {
    "local_buffers": {
      "same_sink_0": {
        "channel": "b040f524-223c-40ad-a620-673d24ba1710",
        "checkpoint": 865,
        "id": "e7a4c0fc-12a9-47b8-9d84-0e2c09b615ef",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "same_source_0": {
        "channel": "b040f524-223c-40ad-a620-673d24ba1710",
        "checkpoint": 865,
        "id": "8d3cc1e3-fe31-47eb-86ee-78b9490bbc41",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 2.24440648199743
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [221.67192357000022, 221.6733425320017] | [341.74686708599984, 341.74929494200114] |
| B | [221.67341989800116, 221.6763792540005] | [341.7494102950004, 341.7513741039984] |
| C | [221.67644646500048, 221.67852134200075] | [341.7514551560016, 341.758506735001] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": 1.285021,
        "p95": 4.085739,
        "p99": 7.281433,
        "samples": 954,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          341.74686708599984,
          341.74929494200114
        ]
      },
      "start": {
        "p50": 1.257751,
        "p95": 4.502708,
        "p99": 6.416758,
        "samples": 375,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          221.67192357000022,
          221.6733425320017
        ]
      }
    },
    "B": {
      "end": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          341.7494102950004,
          341.7513741039984
        ]
      },
      "start": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          221.67341989800116,
          221.6763792540005
        ]
      }
    },
    "C": {
      "end": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          341.7514551560016,
          341.758506735001
        ]
      },
      "start": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          221.67644646500048,
          221.67852134200075
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

#### Recorded repeat 2

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| same_sink_0 | A | 7520000 | 1 | 235 | 2.00173246999 | 119.501825476 | 2.00173246999 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 19281920,
  "extracted_FE": 19281920,
  "residue": {
    "local_buffers": {
      "same_sink_0": {
        "channel": "b040f524-223c-40ad-a620-673d24ba1710",
        "checkpoint": 1817,
        "id": "e7a4c0fc-12a9-47b8-9d84-0e2c09b615ef",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "same_source_0": {
        "channel": "b040f524-223c-40ad-a620-673d24ba1710",
        "checkpoint": 1820,
        "id": "8d3cc1e3-fe31-47eb-86ee-78b9490bbc41",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 0.49628119000408333
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [1860.5818182840012, 1860.5838516270014] | [1980.6646955589968, 1980.6688798989999] |
| B | [1860.5839467900005, 1860.5860656000004] | [1980.6690133599986, 1980.6715975280022] |
| C | [1860.586144369001, 1860.5894217780005] | [1980.6719062010015, 1980.674038721998] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": 1.229519,
        "p95": 4.099054,
        "p99": 11.686776,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1980.6646955589968,
          1980.6688798989999
        ]
      },
      "start": {
        "p50": 1.214625,
        "p95": 3.717947,
        "p99": 8.34918,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1860.5818182840012,
          1860.5838516270014
        ]
      }
    },
    "B": {
      "end": {
        "p50": 1.218379,
        "p95": 3.460392,
        "p99": 6.882942,
        "samples": 1954,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1980.6690133599986,
          1980.6715975280022
        ]
      },
      "start": {
        "p50": 1.218379,
        "p95": 3.460392,
        "p99": 6.882942,
        "samples": 1954,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1860.5839467900005,
          1860.5860656000004
        ]
      }
    },
    "C": {
      "end": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          1980.6719062010015,
          1980.674038721998
        ]
      },
      "start": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          1860.586144369001,
          1860.5894217780005
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

#### Recorded repeat 3

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| same_sink_0 | A | 7520000 | 1 | 235 | 2.001542658 | 119.502050988 | 2.001542658 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 28922880,
  "extracted_FE": 28922880,
  "residue": {
    "local_buffers": {
      "same_sink_0": {
        "channel": "b040f524-223c-40ad-a620-673d24ba1710",
        "checkpoint": 2760,
        "id": "e7a4c0fc-12a9-47b8-9d84-0e2c09b615ef",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "same_source_0": {
        "channel": "b040f524-223c-40ad-a620-673d24ba1710",
        "checkpoint": 2760,
        "id": "8d3cc1e3-fe31-47eb-86ee-78b9490bbc41",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 1.207488246000139
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [2520.8296688440023, 2520.8320075759984] | [2640.910215527001, 2640.912459651998] |
| B | [2520.832130711002, 2520.8338124369984] | [2640.9125714600013, 2640.9141180009974] |
| C | [2520.833891055001, 2520.8355111479977] | [2640.9141812259986, 2640.915722013997] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": 1.245402,
        "p95": 3.635579,
        "p99": 6.692826,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          2640.910215527001,
          2640.912459651998
        ]
      },
      "start": {
        "p50": 1.242601,
        "p95": 3.797421,
        "p99": 8.951498,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          2520.8296688440023,
          2520.8320075759984
        ]
      }
    },
    "B": {
      "end": {
        "p50": 1.210058,
        "p95": 3.43001,
        "p99": 6.356908,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          2640.9125714600013,
          2640.9141180009974
        ]
      },
      "start": {
        "p50": 1.210058,
        "p95": 3.43001,
        "p99": 6.356908,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          2520.832130711002,
          2520.8338124369984
        ]
      }
    },
    "C": {
      "end": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          2640.9141812259986,
          2640.915722013997
        ]
      },
      "start": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          2520.833891055001,
          2520.8355111479977
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

Recorded per-case error totals (missing measurements remain missing):

```json
{
  "low_flow": {
    "SQL_statement_errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "db_deadlock_retries": {
      "measured_samples": 3,
      "sum": 0
    },
    "errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "quarantined": {
      "measured_samples": 3,
      "sum": 0
    },
    "queue_rejected": {
      "measured_samples": 3,
      "sum": 0
    }
  },
  "steady": {
    "SQL_statement_errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "db_deadlock_retries": {
      "measured_samples": 3,
      "sum": 0
    },
    "errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "quarantined": {
      "measured_samples": 3,
      "sum": 0
    },
    "queue_rejected": {
      "measured_samples": 3,
      "sum": 0
    }
  }
}
```

Final case conservation summary (latest cumulative figures, never sum repeated checkpoints):

```json
{
  "all_phase_event_ledger": {
    "accepted_FE": 28922880,
    "extracted_FE": 28922880
  },
  "do_not_sum_repeats": "Conservation values are cumulative per reused channel, not independent repeat totals.",
  "latest_cumulative_accepted_FE": 28922880,
  "latest_cumulative_extracted_FE": 28922880,
  "latest_cumulative_matches_event_ledger": true
}
```

### batch / cross

Case status: complete; missing/incomplete repeats: []; duplicate repeat IDs: FALSE

Recorded topology:

```json
{
  "IO": "Source receiveEnergy -> sink extractEnergy through ct_test; no real chest/machine evidence",
  "dimensions": [
    "minecraft:overworld (ct_test fixture contract)"
  ],
  "lanes": [
    {
      "name": "cross",
      "sinks": [
        "B"
      ],
      "sources": [
        "A"
      ]
    }
  ],
  "neighbor_note": "NeighborPump skips adjacent TesseractBlockEntity; adjacency is not a direct neighbor transfer",
  "per_server_chunk_counts": {
    "A": 1,
    "B": 1
  }
}
```

| Repeat | Reported pass | Recorded complete | Planned attempts | Actual attempts | Steady accepted FE | Steady extracted FE | Steady extracted FE/s | Steady tail to drain FE | SQL tx before final drain | Account statements before final drain |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | TRUE | TRUE | 240 | 240 | 7680000 | 7520000 | 62666.5984755 | 160000 | 1934 | 21490 |
| 2 | TRUE | TRUE | 240 | 240 | 7680000 | 7520000 | 62666.6191774 | 160000 | 1913 | 21360 |
| 3 | TRUE | TRUE | 240 | 240 | 7680000 | 7488000 | 62399.9410981 | 192000 | 1863 | 20918 |

| Repeat | Probes | Full-output lower p50 / p95 / p99 ms | Full-output upper p50 / p95 / p99 ms |
| --- | --- | --- | --- |
| 1 | 40 | 2228.494903 / 2336.192163 / 2344.085227 | 2230.467845 / 2339.550742 / 2346.39208 |
| 2 | 40 | 2225.138524 / 2330.019277 / 2427.489017 | 2226.89354 / 2332.044997 / 2429.411548 |
| 3 | 40 | 2221.877489 / 2328.638918 / 2424.081462 | 2223.539869 / 2330.765721 / 2425.665951 |

| Repeat | SQL transactions | Completed worker tasks | Sql-helper statement attempts | WAL writes | WAL bytes | Identical WAL skips | Batch device appearances | Batch record appearances | Batch payload bytes | Empty batches | Total batch calls (only if explicitly measured) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1934 | 622 | 13848 | 566 | 126310 | 15 | 406 | 1011 | 0 | 275 | UNMEASURED |
| 2 | 1913 | 606 | 13875 | 573 | 132389 | 10 | 380 | 1014 | 0 | 331 | UNMEASURED |
| 3 | 1863 | 590 | 13629 | 558 | 132518 | 14 | 370 | 1011 | 0 | 332 | UNMEASURED |

| Repeat | Worker errors | Queue rejected | Quarantined | Deadlock retries | Account statement errors | All steady recipients served | Sink Jain index | Max sink pull gap s | Failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0 | 0 | 0 | 0 | 0 | TRUE | 1 | 2.002142919 | No recorded failure |
| 2 | 0 | 0 | 0 | 0 | 0 | TRUE | 1 | 2.002332802 | No recorded failure |
| 3 | 0 | 0 | 0 | 0 | 0 | TRUE | 1 | 2.001585585 | No recorded failure |

#### Recorded repeat 1

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cross_sink_0 | B | 7520000 | 1 | 235 | 2.002142919 | 119.502050004 | 2.002142919 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960,
  "residue": {
    "local_buffers": {
      "cross_sink_0": {
        "channel": "487b0bab-6558-4255-a886-527068a456e2",
        "checkpoint": 858,
        "id": "59f85c70-bf39-429e-82fa-297ac089b0ab",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "cross_source_0": {
        "channel": "487b0bab-6558-4255-a886-527068a456e2",
        "checkpoint": 859,
        "id": "a326e933-d0cf-4a43-925e-c9def1b9f299",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 2.186622105000424
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [548.508075351001, 548.5108805819982] | [668.5922170619997, 668.5958637959993] |
| B | [548.511006069999, 548.5128852310008] | [668.5959929400015, 668.5982718009982] |
| C | [548.5130070939995, 548.5157119549986] | [668.5983678849989, 668.6012216000017] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": 1.291319,
        "p95": 4.185818,
        "p99": 6.91048,
        "samples": 1289,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          668.5922170619997,
          668.5958637959993
        ]
      },
      "start": {
        "p50": 1.292822,
        "p95": 4.052866,
        "p99": 7.281433,
        "samples": 1088,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          548.508075351001,
          548.5108805819982
        ]
      }
    },
    "B": {
      "end": {
        "p50": 1.260753,
        "p95": 3.622833,
        "p99": 7.159178,
        "samples": 612,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          668.5959929400015,
          668.5982718009982
        ]
      },
      "start": {
        "p50": 1.364909,
        "p95": 3.622833,
        "p99": 6.785006,
        "samples": 247,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          548.511006069999,
          548.5128852310008
        ]
      }
    },
    "C": {
      "end": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          668.5983678849989,
          668.6012216000017
        ]
      },
      "start": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          548.5130070939995,
          548.5157119549986
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

#### Recorded repeat 2

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cross_sink_0 | B | 7520000 | 1 | 235 | 2.002332802 | 119.501879441 | 2.002332802 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 19281920,
  "extracted_FE": 19281920,
  "residue": {
    "local_buffers": {
      "cross_sink_0": {
        "channel": "487b0bab-6558-4255-a886-527068a456e2",
        "checkpoint": 1738,
        "id": "59f85c70-bf39-429e-82fa-297ac089b0ab",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "cross_source_0": {
        "channel": "487b0bab-6558-4255-a886-527068a456e2",
        "checkpoint": 1739,
        "id": "a326e933-d0cf-4a43-925e-c9def1b9f299",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 2.2470420120007475
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [1200.5582179970006, 1200.5600883969964] | [1320.632690573002, 1320.6349414939978] |
| B | [1200.5601683470013, 1200.5616110650008] | [1320.6350409130027, 1320.6368942069967] |
| C | [1200.561701081002, 1200.5633285560034] | [1320.636960447002, 1320.6389987889997] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": 1.249526,
        "p95": 4.10364,
        "p99": 8.400403,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1320.632690573002,
          1320.6349414939978
        ]
      },
      "start": {
        "p50": 1.253422,
        "p95": 4.197851,
        "p99": 8.400403,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1200.5582179970006,
          1200.5600883969964
        ]
      }
    },
    "B": {
      "end": {
        "p50": 1.212149,
        "p95": 3.483219,
        "p99": 7.159178,
        "samples": 1578,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1320.6350409130027,
          1320.6368942069967
        ]
      },
      "start": {
        "p50": 1.216376,
        "p95": 3.570315,
        "p99": 8.929396,
        "samples": 1221,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1200.5601683470013,
          1200.5616110650008
        ]
      }
    },
    "C": {
      "end": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          1320.636960447002,
          1320.6389987889997
        ]
      },
      "start": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          1200.561701081002,
          1200.5633285560034
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

#### Recorded repeat 3

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cross_sink_0 | B | 7488000 | 1 | 234 | 2.001585585 | 119.501593671 | 2.001585585 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 28922880,
  "extracted_FE": 28922880,
  "residue": {
    "local_buffers": {
      "cross_sink_0": {
        "channel": "487b0bab-6558-4255-a886-527068a456e2",
        "checkpoint": 2613,
        "id": "59f85c70-bf39-429e-82fa-297ac089b0ab",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "cross_source_0": {
        "channel": "487b0bab-6558-4255-a886-527068a456e2",
        "checkpoint": 2613,
        "id": "a326e933-d0cf-4a43-925e-c9def1b9f299",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 1.3196136039987323
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [2849.563175590003, 2849.564752917002] | [2969.6450686359967, 2969.6468697989985] |
| B | [2849.564828351002, 2849.5662044659985] | [2969.6469685679986, 2969.648401147999] |
| C | [2849.5662689029996, 2849.5679416139974] | [2969.6484646929966, 2969.650245746998] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": 1.270217,
        "p95": 3.626315,
        "p99": 6.264468,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          2969.6450686359967,
          2969.6468697989985
        ]
      },
      "start": {
        "p50": 1.265091,
        "p95": 3.635579,
        "p99": 6.692826,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          2849.563175590003,
          2849.564752917002
        ]
      }
    },
    "B": {
      "end": {
        "p50": 1.21271,
        "p95": 3.399941,
        "p99": 6.333145,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          2969.6469685679986,
          2969.648401147999
        ]
      },
      "start": {
        "p50": 1.208307,
        "p95": 3.469431,
        "p99": 7.159178,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          2849.564828351002,
          2849.5662044659985
        ]
      }
    },
    "C": {
      "end": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          2969.6484646929966,
          2969.650245746998
        ]
      },
      "start": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          2849.5662689029996,
          2849.5679416139974
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

Recorded per-case error totals (missing measurements remain missing):

```json
{
  "low_flow": {
    "SQL_statement_errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "db_deadlock_retries": {
      "measured_samples": 3,
      "sum": 0
    },
    "errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "quarantined": {
      "measured_samples": 3,
      "sum": 0
    },
    "queue_rejected": {
      "measured_samples": 3,
      "sum": 0
    }
  },
  "steady": {
    "SQL_statement_errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "db_deadlock_retries": {
      "measured_samples": 3,
      "sum": 0
    },
    "errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "quarantined": {
      "measured_samples": 3,
      "sum": 0
    },
    "queue_rejected": {
      "measured_samples": 3,
      "sum": 0
    }
  }
}
```

Final case conservation summary (latest cumulative figures, never sum repeated checkpoints):

```json
{
  "all_phase_event_ledger": {
    "accepted_FE": 28922880,
    "extracted_FE": 28922880
  },
  "do_not_sum_repeats": "Conservation values are cumulative per reused channel, not independent repeat totals.",
  "latest_cumulative_accepted_FE": 28922880,
  "latest_cumulative_extracted_FE": 28922880,
  "latest_cumulative_matches_event_ledger": true
}
```

### batch / mixed

Case status: complete; missing/incomplete repeats: []; duplicate repeat IDs: FALSE

Recorded topology:

```json
{
  "IO": "Source receiveEnergy -> sink extractEnergy through ct_test; no real chest/machine evidence",
  "dimensions": [
    "minecraft:overworld (ct_test fixture contract)"
  ],
  "lanes": [
    {
      "name": "mixed",
      "sinks": [
        "A",
        "B"
      ],
      "sources": [
        "A"
      ]
    }
  ],
  "neighbor_note": "NeighborPump skips adjacent TesseractBlockEntity; adjacency is not a direct neighbor transfer",
  "per_server_chunk_counts": {
    "A": 1,
    "B": 1
  }
}
```

| Repeat | Reported pass | Recorded complete | Planned attempts | Actual attempts | Steady accepted FE | Steady extracted FE | Steady extracted FE/s | Steady tail to drain FE | SQL tx before final drain | Account statements before final drain |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | TRUE | TRUE | 240 | 240 | 7680000 | 7552000 | 62933.2840928 | 128000 | 2018 | 22725 |
| 2 | TRUE | TRUE | 240 | 240 | 7680000 | 7520000 | 62666.6167595 | 160000 | 2039 | 22997 |
| 3 | TRUE | TRUE | 240 | 240 | 7680000 | 7520000 | 62666.6116516 | 160000 | 2063 | 23296 |

| Repeat | Probes | Full-output lower p50 / p95 / p99 ms | Full-output upper p50 / p95 / p99 ms |
| --- | --- | --- | --- |
| 1 | 40 | 2242.72361 / 2342.231267 / 2356.365761 | 2244.661328 / 2344.613303 / 2358.895169 |
| 2 | 40 | 2145.490239 / 2351.945561 / 2545.817883 | 2147.380758 / 2353.64522 / 2547.895724 |
| 3 | 40 | 2234.872794 / 2340.485235 / 2354.951527 | 2236.723916 / 2342.174277 / 2357.044283 |

| Repeat | SQL transactions | Completed worker tasks | Sql-helper statement attempts | WAL writes | WAL bytes | Identical WAL skips | Batch device appearances | Batch record appearances | Batch payload bytes | Empty batches | Total batch calls (only if explicitly measured) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2018 | 743 | 14312 | 651 | 116731 | 12 | 537 | 956 | 0 | 277 | UNMEASURED |
| 2 | 2039 | 752 | 14467 | 659 | 117691 | 12 | 543 | 962 | 0 | 276 | UNMEASURED |
| 3 | 2063 | 748 | 14692 | 660 | 117892 | 12 | 550 | 976 | 0 | 262 | UNMEASURED |

| Repeat | Worker errors | Queue rejected | Quarantined | Deadlock retries | Account statement errors | All steady recipients served | Sink Jain index | Max sink pull gap s | Failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0 | 0 | 0 | 0 | 0 | TRUE | 0.999928186715 | 5.000193689 | No recorded failure |
| 2 | 0 | 0 | 0 | 0 | 0 | TRUE | 0.999113507255 | 5.000260823 | No recorded failure |
| 3 | 0 | 0 | 0 | 0 | 0 | TRUE | 0.990511891523 | 4.49947787701 | No recorded failure |

#### Recorded repeat 1

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| mixed_sink_0 | A | 3744000 | 0.495762711864 | 117 | 2.001587325 | 119.502746044 | 5.000193689 |
| mixed_sink_1 | B | 3808000 | 0.504237288136 | 119 | 2.50154348 | 119.502231192 | 5.000177138 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960,
  "residue": {
    "local_buffers": {
      "mixed_sink_0": {
        "channel": "4afd5847-66eb-44f7-8a29-58b4d5e44b96",
        "checkpoint": 427,
        "id": "5928b263-7194-4cbb-a88d-7fd4d53f0a89",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "mixed_sink_1": {
        "channel": "4afd5847-66eb-44f7-8a29-58b4d5e44b96",
        "checkpoint": 420,
        "id": "f3cc08b9-f69e-414a-8a43-882f48cbd5be",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "mixed_source_0": {
        "channel": "4afd5847-66eb-44f7-8a29-58b4d5e44b96",
        "checkpoint": 847,
        "id": "2e60f9e4-fa49-463c-b578-6f580d50ca22",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 1.1113807979927515
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [877.7250468989987, 877.7269756489986] | [997.8057339520019, 997.8080587009972] |
| B | [877.7270584729995, 877.7287517900004] | [997.8082112600023, 997.8107276169976] |
| C | [877.7288468029983, 877.730943691] | [997.8107896299989, 997.8128867280029] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": 1.266783,
        "p95": 4.052866,
        "p99": 8.760433,
        "samples": 1981,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          997.8057339520019,
          997.8080587009972
        ]
      },
      "start": {
        "p50": 1.291106,
        "p95": 4.042163,
        "p99": 6.416758,
        "samples": 1557,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          877.7250468989987,
          877.7269756489986
        ]
      }
    },
    "B": {
      "end": {
        "p50": 1.227673,
        "p95": 3.643329,
        "p99": 12.631058,
        "samples": 980,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          997.8082112600023,
          997.8107276169976
        ]
      },
      "start": {
        "p50": 1.253402,
        "p95": 3.643329,
        "p99": 7.245767,
        "samples": 753,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          877.7270584729995,
          877.7287517900004
        ]
      }
    },
    "C": {
      "end": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          997.8107896299989,
          997.8128867280029
        ]
      },
      "start": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          877.7288468029983,
          877.730943691
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

#### Recorded repeat 2

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| mixed_sink_0 | A | 3648000 | 0.485106382979 | 114 | 2.001574834 | 117.001340983 | 3.500836039 |
| mixed_sink_1 | B | 3872000 | 0.514893617021 | 121 | 1.501737655 | 119.001998029 | 5.000260823 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 19281920,
  "extracted_FE": 19281920,
  "residue": {
    "local_buffers": {
      "mixed_sink_0": {
        "channel": "4afd5847-66eb-44f7-8a29-58b4d5e44b96",
        "checkpoint": 844,
        "id": "5928b263-7194-4cbb-a88d-7fd4d53f0a89",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "mixed_sink_1": {
        "channel": "4afd5847-66eb-44f7-8a29-58b4d5e44b96",
        "checkpoint": 850,
        "id": "f3cc08b9-f69e-414a-8a43-882f48cbd5be",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "mixed_source_0": {
        "channel": "4afd5847-66eb-44f7-8a29-58b4d5e44b96",
        "checkpoint": 1694,
        "id": "2e60f9e4-fa49-463c-b578-6f580d50ca22",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 0.7596831609989749
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [1529.519930059003, 1529.5214067159977] | [1649.600265811001, 1649.6025867450007] |
| B | [1529.5214827699965, 1529.522947999998] | [1649.602698984003, 1649.6043160469999] |
| C | [1529.523006176998, 1529.5250266910007] | [1649.6044007640012, 1649.6066046429987] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": 1.233593,
        "p95": 3.957421,
        "p99": 8.34918,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1649.600265811001,
          1649.6025867450007
        ]
      },
      "start": {
        "p50": 1.250738,
        "p95": 4.197851,
        "p99": 8.760433,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1529.519930059003,
          1529.5214067159977
        ]
      }
    },
    "B": {
      "end": {
        "p50": 1.218319,
        "p95": 3.460392,
        "p99": 6.882942,
        "samples": 1950,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1649.602698984003,
          1649.6043160469999
        ]
      },
      "start": {
        "p50": 1.214743,
        "p95": 3.460392,
        "p99": 6.908049,
        "samples": 1718,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1529.5214827699965,
          1529.522947999998
        ]
      }
    },
    "C": {
      "end": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          1649.6044007640012,
          1649.6066046429987
        ]
      },
      "start": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          1529.523006176998,
          1529.5250266910007
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

#### Recorded repeat 3

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| mixed_sink_0 | A | 4128000 | 0.548936170213 | 129 | 2.501861714 | 118.005847373 | 3.500569516 |
| mixed_sink_1 | B | 3392000 | 0.451063829787 | 106 | 3.001997903 | 119.5016964 | 4.49947787701 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 28922880,
  "extracted_FE": 28922880,
  "residue": {
    "local_buffers": {
      "mixed_sink_0": {
        "channel": "4afd5847-66eb-44f7-8a29-58b4d5e44b96",
        "checkpoint": 1302,
        "id": "5928b263-7194-4cbb-a88d-7fd4d53f0a89",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "mixed_sink_1": {
        "channel": "4afd5847-66eb-44f7-8a29-58b4d5e44b96",
        "checkpoint": 1275,
        "id": "f3cc08b9-f69e-414a-8a43-882f48cbd5be",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "mixed_source_0": {
        "channel": "4afd5847-66eb-44f7-8a29-58b4d5e44b96",
        "checkpoint": 2577,
        "id": "2e60f9e4-fa49-463c-b578-6f580d50ca22",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 1.726867808996758
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [2190.334832323999, 2190.336641312002] | [2310.4068155589994, 2310.4089117480034] |
| B | [2190.336753921001, 2190.3383811349995] | [2310.409072328999, 2310.4109329939965] |
| C | [2190.3384908399967, 2190.340179316001] | [2310.4110413969975, 2310.413968754001] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": 1.235395,
        "p95": 3.726814,
        "p99": 8.951498,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          2310.4068155589994,
          2310.4089117480034
        ]
      },
      "start": {
        "p50": 1.238405,
        "p95": 3.803013,
        "p99": 9.247592,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          2190.334832323999,
          2190.336641312002
        ]
      }
    },
    "B": {
      "end": {
        "p50": 1.210027,
        "p95": 3.43001,
        "p99": 6.356908,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          2310.409072328999,
          2310.4109329939965
        ]
      },
      "start": {
        "p50": 1.222936,
        "p95": 3.469431,
        "p99": 6.882942,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          2190.336753921001,
          2190.3383811349995
        ]
      }
    },
    "C": {
      "end": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          2310.4110413969975,
          2310.413968754001
        ]
      },
      "start": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          2190.3384908399967,
          2190.340179316001
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

Recorded per-case error totals (missing measurements remain missing):

```json
{
  "low_flow": {
    "SQL_statement_errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "db_deadlock_retries": {
      "measured_samples": 3,
      "sum": 0
    },
    "errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "quarantined": {
      "measured_samples": 3,
      "sum": 0
    },
    "queue_rejected": {
      "measured_samples": 3,
      "sum": 0
    }
  },
  "steady": {
    "SQL_statement_errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "db_deadlock_retries": {
      "measured_samples": 3,
      "sum": 0
    },
    "errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "quarantined": {
      "measured_samples": 3,
      "sum": 0
    },
    "queue_rejected": {
      "measured_samples": 3,
      "sum": 0
    }
  }
}
```

Final case conservation summary (latest cumulative figures, never sum repeated checkpoints):

```json
{
  "all_phase_event_ledger": {
    "accepted_FE": 28922880,
    "extracted_FE": 28922880
  },
  "do_not_sum_repeats": "Conservation values are cumulative per reused channel, not independent repeat totals.",
  "latest_cumulative_accepted_FE": 28922880,
  "latest_cumulative_extracted_FE": 28922880,
  "latest_cumulative_matches_event_ledger": true
}
```

### fast / same

Case status: complete; missing/incomplete repeats: []; duplicate repeat IDs: FALSE

Recorded topology:

```json
{
  "IO": "Source receiveEnergy -> sink extractEnergy through ct_test; no real chest/machine evidence",
  "dimensions": [
    "minecraft:overworld (ct_test fixture contract)"
  ],
  "lanes": [
    {
      "name": "same",
      "sinks": [
        "A"
      ],
      "sources": [
        "A"
      ]
    }
  ],
  "neighbor_note": "NeighborPump skips adjacent TesseractBlockEntity; adjacency is not a direct neighbor transfer",
  "per_server_chunk_counts": {
    "A": 1
  }
}
```

| Repeat | Reported pass | Recorded complete | Planned attempts | Actual attempts | Steady accepted FE | Steady extracted FE | Steady extracted FE/s | Steady tail to drain FE | SQL tx before final drain | Account statements before final drain |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | TRUE | TRUE | 240 | 240 | 7680000 | 7648000 | 63733.296598 | 32000 | 2417 | 31638 |
| 2 | TRUE | TRUE | 240 | 240 | 7680000 | 7616000 | 63466.5977509 | 64000 | 2446 | 32786 |
| 3 | TRUE | TRUE | 240 | 240 | 7680000 | 7648000 | 63733.260516 | 32000 | 2425 | 31788 |

| Repeat | Probes | Full-output lower p50 / p95 / p99 ms | Full-output upper p50 / p95 / p99 ms |
| --- | --- | --- | --- |
| 1 | 40 | 202.530014001 / 205.263768003 / 207.559410002 | 205.997644 / 209.546596998 / 211.176049001 |
| 2 | 40 | 302.858057999 / 404.003559001 / 409.923405001 | 304.863192003 / 405.903973995 / 412.019374999 |
| 3 | 40 | 302.974728002 / 404.178204 / 407.553716002 | 305.046032001 / 406.243393001 / 410.364926 |

| Repeat | SQL transactions | Completed worker tasks | Sql-helper statement attempts | WAL writes | WAL bytes | Identical WAL skips | Batch device appearances | Batch record appearances | Batch payload bytes | Empty batches | Total batch calls (only if explicitly measured) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2417 | 791 | 20743 | 1200 | 202728 | 0 | 791 | 1341 | 0 | 296 | UNMEASURED |
| 2 | 2446 | 820 | 21683 | 1199 | 227095 | 0 | 820 | 1671 | 0 | 295 | UNMEASURED |
| 3 | 2425 | 800 | 20822 | 1199 | 202687 | 0 | 800 | 1360 | 0 | 262 | UNMEASURED |

| Repeat | Worker errors | Queue rejected | Quarantined | Deadlock retries | Account statement errors | All steady recipients served | Sink Jain index | Max sink pull gap s | Failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0 | 0 | 0 | 0 | 0 | TRUE | 1 | 0.504488207996 | No recorded failure |
| 2 | 0 | 0 | 0 | 0 | 0 | TRUE | 1 | 0.999886452002 | No recorded failure |
| 3 | 0 | 0 | 0 | 0 | 0 | TRUE | 1 | 0.511564127999 | No recorded failure |

#### Recorded repeat 1

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| same_sink_0 | A | 7648000 | 1 | 239 | 0.502066601999 | 119.501556285 | 0.504488207996 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960,
  "residue": {
    "local_buffers": {
      "same_sink_0": {
        "channel": "a8b5d529-86f3-4be4-9f0a-f413a9907c40",
        "checkpoint": 1359,
        "id": "2323c6fc-a9ff-4dde-adab-c5e0ffbbfe9b",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "same_source_0": {
        "channel": "a8b5d529-86f3-4be4-9f0a-f413a9907c40",
        "checkpoint": 1360,
        "id": "4383cba7-f162-4037-bb9e-e8568518e16a",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 0.08889871300198138
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [139.42203345799498, 139.42490098100097] | [259.5082710220013, 259.5110602729983] |
| B | [139.4250090429996, 139.42859345299803] | [259.5111709490011, 259.5137180919992] |
| C | [139.43012669299787, 139.43305470699852] | [259.51379040999745, 259.51642616099707] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": 1.20553,
        "p95": 3.340181,
        "p99": 5.826427,
        "samples": 1740,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          259.5082710220013,
          259.5110602729983
        ]
      },
      "start": {
        "p50": 1.34257,
        "p95": 3.9576,
        "p99": 6.82709,
        "samples": 540,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          139.42203345799498,
          139.42490098100097
        ]
      }
    },
    "B": {
      "end": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          259.5111709490011,
          259.5137180919992
        ]
      },
      "start": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          139.4250090429996,
          139.42859345299803
        ]
      }
    },
    "C": {
      "end": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          259.51379040999745,
          259.51642616099707
        ]
      },
      "start": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          139.43012669299787,
          139.43305470699852
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

#### Recorded repeat 2

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| same_sink_0 | A | 7616000 | 1 | 238 | 0.501441836997 | 119.502332106 | 0.999886452002 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 19281920,
  "extracted_FE": 19281920,
  "residue": {
    "local_buffers": {
      "same_sink_0": {
        "channel": "a8b5d529-86f3-4be4-9f0a-f413a9907c40",
        "checkpoint": 2719,
        "id": "2323c6fc-a9ff-4dde-adab-c5e0ffbbfe9b",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "same_source_0": {
        "channel": "a8b5d529-86f3-4be4-9f0a-f413a9907c40",
        "checkpoint": 2720,
        "id": "4383cba7-f162-4037-bb9e-e8568518e16a",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 0.1798761399986688
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [1399.435644254001, 1399.437612140995] | [1519.5192240179967, 1519.5216690399975] |
| B | [1399.4376943940006, 1399.4395406879994] | [1519.521797673995, 1519.5249153959958] |
| C | [1399.4396100629965, 1399.4420514199956] | [1519.52501148, 1519.5268690000012] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": 1.162677,
        "p95": 3.414187,
        "p99": 7.309916,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1519.5192240179967,
          1519.5216690399975
        ]
      },
      "start": {
        "p50": 1.214717,
        "p95": 3.408288,
        "p99": 6.273759,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1399.435644254001,
          1399.437612140995
        ]
      }
    },
    "B": {
      "end": {
        "p50": 1.258059,
        "p95": 3.602147,
        "p99": 6.617249,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1519.521797673995,
          1519.5249153959958
        ]
      },
      "start": {
        "p50": 1.258059,
        "p95": 3.602147,
        "p99": 6.617249,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1399.4376943940006,
          1399.4395406879994
        ]
      }
    },
    "C": {
      "end": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          1519.52501148,
          1519.5268690000012
        ]
      },
      "start": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          1399.4396100629965,
          1399.4420514199956
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

#### Recorded repeat 3

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| same_sink_0 | A | 7648000 | 1 | 239 | 0.501889510997 | 119.501522735 | 0.511564127999 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 28922880,
  "extracted_FE": 28922880,
  "residue": {
    "local_buffers": {
      "same_sink_0": {
        "channel": "a8b5d529-86f3-4be4-9f0a-f413a9907c40",
        "checkpoint": 4080,
        "id": "2323c6fc-a9ff-4dde-adab-c5e0ffbbfe9b",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "same_source_0": {
        "channel": "a8b5d529-86f3-4be4-9f0a-f413a9907c40",
        "checkpoint": 4080,
        "id": "4383cba7-f162-4037-bb9e-e8568518e16a",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 0.097283133000019
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [1906.1447894579978, 1906.1464324339977] | [2026.2263418669972, 2026.2282326249988] |
| B | [1906.1465433609992, 1906.1484537590004] | [2026.2283995459948, 2026.232084917996] |
| C | [1906.1485273989965, 1906.1503722689959] | [2026.2321733709978, 2026.233934183998] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": 1.116666,
        "p95": 3.133965,
        "p99": 5.434158,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          2026.2263418669972,
          2026.2282326249988
        ]
      },
      "start": {
        "p50": 1.143407,
        "p95": 3.403996,
        "p99": 6.28012,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1906.1447894579978,
          1906.1464324339977
        ]
      }
    },
    "B": {
      "end": {
        "p50": 1.264831,
        "p95": 3.602147,
        "p99": 5.812555,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          2026.2283995459948,
          2026.232084917996
        ]
      },
      "start": {
        "p50": 1.264831,
        "p95": 3.602147,
        "p99": 5.812555,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1906.1465433609992,
          1906.1484537590004
        ]
      }
    },
    "C": {
      "end": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          2026.2321733709978,
          2026.233934183998
        ]
      },
      "start": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          1906.1485273989965,
          1906.1503722689959
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

Recorded per-case error totals (missing measurements remain missing):

```json
{
  "low_flow": {
    "SQL_statement_errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "db_deadlock_retries": {
      "measured_samples": 3,
      "sum": 0
    },
    "errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "quarantined": {
      "measured_samples": 3,
      "sum": 0
    },
    "queue_rejected": {
      "measured_samples": 3,
      "sum": 0
    }
  },
  "steady": {
    "SQL_statement_errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "db_deadlock_retries": {
      "measured_samples": 3,
      "sum": 0
    },
    "errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "quarantined": {
      "measured_samples": 3,
      "sum": 0
    },
    "queue_rejected": {
      "measured_samples": 3,
      "sum": 0
    }
  }
}
```

Final case conservation summary (latest cumulative figures, never sum repeated checkpoints):

```json
{
  "all_phase_event_ledger": {
    "accepted_FE": 28922880,
    "extracted_FE": 28922880
  },
  "do_not_sum_repeats": "Conservation values are cumulative per reused channel, not independent repeat totals.",
  "latest_cumulative_accepted_FE": 28922880,
  "latest_cumulative_extracted_FE": 28922880,
  "latest_cumulative_matches_event_ledger": true
}
```

### fast / cross

Case status: complete; missing/incomplete repeats: []; duplicate repeat IDs: FALSE

Recorded topology:

```json
{
  "IO": "Source receiveEnergy -> sink extractEnergy through ct_test; no real chest/machine evidence",
  "dimensions": [
    "minecraft:overworld (ct_test fixture contract)"
  ],
  "lanes": [
    {
      "name": "cross",
      "sinks": [
        "B"
      ],
      "sources": [
        "A"
      ]
    }
  ],
  "neighbor_note": "NeighborPump skips adjacent TesseractBlockEntity; adjacency is not a direct neighbor transfer",
  "per_server_chunk_counts": {
    "A": 1,
    "B": 1
  }
}
```

| Repeat | Reported pass | Recorded complete | Planned attempts | Actual attempts | Steady accepted FE | Steady extracted FE | Steady extracted FE/s | Steady tail to drain FE | SQL tx before final drain | Account statements before final drain |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | TRUE | TRUE | 240 | 240 | 7680000 | 7616000 | 63466.6113698 | 64000 | 3689 | 42545 |
| 2 | TRUE | TRUE | 240 | 240 | 7680000 | 7648000 | 63733.2308094 | 32000 | 3545 | 39335 |
| 3 | TRUE | TRUE | 240 | 240 | 7680000 | 7616000 | 63466.6154063 | 64000 | 3720 | 43419 |

| Repeat | Probes | Full-output lower p50 / p95 / p99 ms | Full-output upper p50 / p95 / p99 ms |
| --- | --- | --- | --- |
| 1 | 40 | 304.858067 / 408.042330004 / 410.731381999 | 307.834558997 / 411.434603004 / 414.521948005 |
| 2 | 40 | 505.435257 / 509.381627999 / 607.553875998 | 507.676036003 / 511.255942998 / 610.301891997 |
| 3 | 40 | 404.494859002 / 506.057916995 / 606.817213004 | 406.658720007 / 509.594960997 / 608.764842 |

| Repeat | SQL transactions | Completed worker tasks | Sql-helper statement attempts | WAL writes | WAL bytes | Identical WAL skips | Batch device appearances | Batch record appearances | Batch payload bytes | Empty batches | Total batch calls (only if explicitly measured) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 3689 | 1405 | 27277 | 1404 | 252852 | 0 | 925 | 1672 | 0 | 534 | UNMEASURED |
| 2 | 3545 | 1269 | 25065 | 1200 | 202728 | 0 | 789 | 1337 | 0 | 534 | UNMEASURED |
| 3 | 3720 | 1433 | 27962 | 1432 | 270200 | 0 | 953 | 1860 | 0 | 479 | UNMEASURED |

| Repeat | Worker errors | Queue rejected | Quarantined | Deadlock retries | Account statement errors | All steady recipients served | Sink Jain index | Max sink pull gap s | Failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0 | 0 | 0 | 0 | 0 | TRUE | 1 | 1.001052448 | No recorded failure |
| 2 | 0 | 0 | 0 | 0 | 0 | TRUE | 1 | 0.505318523996 | No recorded failure |
| 3 | 0 | 0 | 0 | 0 | 0 | TRUE | 1 | 1.000204266 | No recorded failure |

#### Recorded repeat 1

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cross_sink_0 | B | 7616000 | 1 | 238 | 0.502302599998 | 119.502345309 | 1.001052448 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960,
  "residue": {
    "local_buffers": {
      "cross_sink_0": {
        "channel": "e9f6fedb-4e37-4192-ad74-df8504705f8d",
        "checkpoint": 1360,
        "id": "9d887f39-bd3f-4f1d-ba5a-f3429362ad80",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "cross_source_0": {
        "channel": "e9f6fedb-4e37-4192-ad74-df8504705f8d",
        "checkpoint": 1360,
        "id": "c4e7a65a-0730-42b9-a6a2-4024cffc7b05",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 0.1907178350011236
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [391.1306198969978, 391.1337716929993] | [511.2154879199952, 511.2180347850008] |
| B | [391.13390239, 391.13862804100063] | [511.21813040800043, 511.2217334789966] |
| C | [391.13872665899544, 391.14106327999616] | [511.22180885199487, 511.2239777989962] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": 1.154295,
        "p95": 3.211674,
        "p99": 6.538404,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          511.2154879199952,
          511.2180347850008
        ]
      },
      "start": {
        "p50": 1.203948,
        "p95": 3.426137,
        "p99": 6.133697,
        "samples": 1942,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          391.1306198969978,
          391.1337716929993
        ]
      }
    },
    "B": {
      "end": {
        "p50": 1.259923,
        "p95": 4.425504,
        "p99": 9.13049,
        "samples": 1320,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          511.21813040800043,
          511.2217334789966
        ]
      },
      "start": {
        "p50": 1.295828,
        "p95": 4.820553,
        "p99": 18.802003,
        "samples": 396,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          391.13390239,
          391.13862804100063
        ]
      }
    },
    "C": {
      "end": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          511.22180885199487,
          511.2239777989962
        ]
      },
      "start": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          391.13872665899544,
          391.14106327999616
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

#### Recorded repeat 2

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cross_sink_0 | B | 7648000 | 1 | 239 | 0.501664134004 | 119.5017215 | 0.505318523996 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 19281920,
  "extracted_FE": 19281920,
  "residue": {
    "local_buffers": {
      "cross_sink_0": {
        "channel": "e9f6fedb-4e37-4192-ad74-df8504705f8d",
        "checkpoint": 2720,
        "id": "9d887f39-bd3f-4f1d-ba5a-f3429362ad80",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "cross_source_0": {
        "channel": "e9f6fedb-4e37-4192-ad74-df8504705f8d",
        "checkpoint": 2720,
        "id": "c4e7a65a-0730-42b9-a6a2-4024cffc7b05",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 0.09447677099524299
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [898.1527437740006, 898.1542469209962] | [1018.2301355429954, 1018.2319247889973] |
| B | [898.154358187996, 898.1559586609947] | [1018.2320197410008, 1018.2340689369958] |
| C | [898.1560222659973, 898.1580473759968] | [1018.2341348959962, 1018.2359013879977] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": 1.247122,
        "p95": 4.579014,
        "p99": 19.552175,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1018.2301355429954,
          1018.2319247889973
        ]
      },
      "start": {
        "p50": 1.177788,
        "p95": 4.271849,
        "p99": 19.719661,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          898.1527437740006,
          898.1542469209962
        ]
      }
    },
    "B": {
      "end": {
        "p50": 1.251819,
        "p95": 3.762138,
        "p99": 8.970729,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1018.2320197410008,
          1018.2340689369958
        ]
      },
      "start": {
        "p50": 1.239802,
        "p95": 4.039477,
        "p99": 9.781057,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          898.154358187996,
          898.1559586609947
        ]
      }
    },
    "C": {
      "end": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          1018.2341348959962,
          1018.2359013879977
        ]
      },
      "start": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          898.1560222659973,
          898.1580473759968
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

#### Recorded repeat 3

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cross_sink_0 | B | 7616000 | 1 | 238 | 0.501748385002 | 119.502025895 | 1.000204266 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 28922880,
  "extracted_FE": 28922880,
  "residue": {
    "local_buffers": {
      "cross_sink_0": {
        "channel": "e9f6fedb-4e37-4192-ad74-df8504705f8d",
        "checkpoint": 4080,
        "id": "9d887f39-bd3f-4f1d-ba5a-f3429362ad80",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "cross_source_0": {
        "channel": "e9f6fedb-4e37-4192-ad74-df8504705f8d",
        "checkpoint": 4080,
        "id": "c4e7a65a-0730-42b9-a6a2-4024cffc7b05",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 0.1917932189971907
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [2162.2797649569984, 2162.2811274769992] | [2282.363644482997, 2282.3660034589993] |
| B | [2162.2812052539957, 2162.282552331999] | [2282.3662056629983, 2282.3678350929986] |
| C | [2162.282610800001, 2162.2843525709977] | [2282.367907701999, 2282.3697957599943] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": 1.05047,
        "p95": 3.131711,
        "p99": 6.082086,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          2282.363644482997,
          2282.3660034589993
        ]
      },
      "start": {
        "p50": 1.104688,
        "p95": 3.140314,
        "p99": 5.440357,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          2162.2797649569984,
          2162.2811274769992
        ]
      }
    },
    "B": {
      "end": {
        "p50": 1.173024,
        "p95": 3.341037,
        "p99": 5.572208,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          2282.3662056629983,
          2282.3678350929986
        ]
      },
      "start": {
        "p50": 1.248736,
        "p95": 3.541778,
        "p99": 5.572208,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          2162.2812052539957,
          2162.282552331999
        ]
      }
    },
    "C": {
      "end": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          2282.367907701999,
          2282.3697957599943
        ]
      },
      "start": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          2162.282610800001,
          2162.2843525709977
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

Recorded per-case error totals (missing measurements remain missing):

```json
{
  "low_flow": {
    "SQL_statement_errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "db_deadlock_retries": {
      "measured_samples": 3,
      "sum": 0
    },
    "errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "quarantined": {
      "measured_samples": 3,
      "sum": 0
    },
    "queue_rejected": {
      "measured_samples": 3,
      "sum": 0
    }
  },
  "steady": {
    "SQL_statement_errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "db_deadlock_retries": {
      "measured_samples": 3,
      "sum": 0
    },
    "errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "quarantined": {
      "measured_samples": 3,
      "sum": 0
    },
    "queue_rejected": {
      "measured_samples": 3,
      "sum": 0
    }
  }
}
```

Final case conservation summary (latest cumulative figures, never sum repeated checkpoints):

```json
{
  "all_phase_event_ledger": {
    "accepted_FE": 28922880,
    "extracted_FE": 28922880
  },
  "do_not_sum_repeats": "Conservation values are cumulative per reused channel, not independent repeat totals.",
  "latest_cumulative_accepted_FE": 28922880,
  "latest_cumulative_extracted_FE": 28922880,
  "latest_cumulative_matches_event_ledger": true
}
```

### fast / mixed

Case status: complete; missing/incomplete repeats: []; duplicate repeat IDs: FALSE

Recorded topology:

```json
{
  "IO": "Source receiveEnergy -> sink extractEnergy through ct_test; no real chest/machine evidence",
  "dimensions": [
    "minecraft:overworld (ct_test fixture contract)"
  ],
  "lanes": [
    {
      "name": "mixed",
      "sinks": [
        "A",
        "B"
      ],
      "sources": [
        "A"
      ]
    }
  ],
  "neighbor_note": "NeighborPump skips adjacent TesseractBlockEntity; adjacency is not a direct neighbor transfer",
  "per_server_chunk_counts": {
    "A": 1,
    "B": 1
  }
}
```

| Repeat | Reported pass | Recorded complete | Planned attempts | Actual attempts | Steady accepted FE | Steady extracted FE | Steady extracted FE/s | Steady tail to drain FE | SQL tx before final drain | Account statements before final drain |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | TRUE | TRUE | 240 | 240 | 7680000 | 7648000 | 63733.2704785 | 32000 | 3250 | 41199 |
| 2 | TRUE | TRUE | 240 | 240 | 7680000 | 7648000 | 63733.0486978 | 32000 | 3341 | 42672 |
| 3 | TRUE | TRUE | 240 | 240 | 7680000 | 7648000 | 63733.265434 | 32000 | 3346 | 42796 |

| Repeat | Probes | Full-output lower p50 / p95 / p99 ms | Full-output upper p50 / p95 / p99 ms |
| --- | --- | --- | --- |
| 1 | 40 | 204.721621005 / 408.411313001 / 409.328459995 | 207.586056 / 410.680841 / 411.700472003 |
| 2 | 40 | 207.969561001 / 407.684682003 / 413.574870996 | 210.438335998 / 409.645877 / 417.713238996 |
| 3 | 40 | 407.299578001 / 513.402034005 / 516.839092001 | 409.836093 / 515.585533001 / 519.187098005 |

| Repeat | SQL transactions | Completed worker tasks | Sql-helper statement attempts | WAL writes | WAL bytes | Identical WAL skips | Batch device appearances | Batch record appearances | Batch payload bytes | Empty batches | Total batch calls (only if explicitly measured) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 3250 | 1320 | 26175 | 1438 | 229550 | 0 | 1200 | 1679 | 0 | 305 | UNMEASURED |
| 2 | 3341 | 1417 | 26981 | 1420 | 226580 | 0 | 1297 | 1781 | 0 | 307 | UNMEASURED |
| 3 | 3346 | 1420 | 27062 | 1438 | 229622 | 0 | 1300 | 1783 | 0 | 320 | UNMEASURED |

| Repeat | Worker errors | Queue rejected | Quarantined | Deadlock retries | Account statement errors | All steady recipients served | Sink Jain index | Max sink pull gap s | Failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0 | 0 | 0 | 0 | 0 | TRUE | 0.99998249361 | 1.499891009 | No recorded failure |
| 2 | 0 | 0 | 0 | 0 | 0 | TRUE | 0.99998249361 | 1.502321105 | No recorded failure |
| 3 | 0 | 0 | 0 | 0 | 0 | TRUE | 0.99998249361 | 1.499662345 | No recorded failure |

#### Recorded repeat 1

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| mixed_sink_0 | A | 3840000 | 0.502092050209 | 120 | 0.502479696996 | 119.503006586 | 1.00340045 |
| mixed_sink_1 | B | 3808000 | 0.497907949791 | 119 | 1.002281663 | 119.003575059 | 1.499891009 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960,
  "residue": {
    "local_buffers": {
      "mixed_sink_0": {
        "channel": "2e657e3e-f2f7-4cfb-9270-e27408c0f096",
        "checkpoint": 680,
        "id": "091c2bf3-6fc3-4f1d-9775-37ef690561fd",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "mixed_sink_1": {
        "channel": "2e657e3e-f2f7-4cfb-9270-e27408c0f096",
        "checkpoint": 680,
        "id": "b3e29c68-cb15-462b-8f95-15d73e74faff",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "mixed_source_0": {
        "channel": "2e657e3e-f2f7-4cfb-9270-e27408c0f096",
        "checkpoint": 1360,
        "id": "70427d3c-f891-4f39-af5e-6071d2c24b24",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 0.08780798700172454
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [640.3714020240004, 640.3732536839962] | [760.4552641389964, 760.4583778140004] |
| B | [640.373378090997, 640.3751717129999] | [760.4584773829993, 760.4609163849964] |
| C | [640.3752526749959, 640.3775377450002] | [760.461167180998, 760.4638310109949] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": 1.183416,
        "p95": 4.407512,
        "p99": 19.719661,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          760.4552641389964,
          760.4583778140004
        ]
      },
      "start": {
        "p50": 1.145342,
        "p95": 3.246423,
        "p99": 6.357011,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          640.3714020240004,
          640.3732536839962
        ]
      }
    },
    "B": {
      "end": {
        "p50": 1.258651,
        "p95": 4.434368,
        "p99": 12.366773,
        "samples": 1999,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          760.4584773829993,
          760.4609163849964
        ]
      },
      "start": {
        "p50": 1.259016,
        "p95": 4.4205,
        "p99": 8.57842,
        "samples": 1521,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          640.373378090997,
          640.3751717129999
        ]
      }
    },
    "C": {
      "end": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          760.461167180998,
          760.4638310109949
        ]
      },
      "start": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          640.3752526749959,
          640.3775377450002
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

#### Recorded repeat 2

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| mixed_sink_0 | A | 3840000 | 0.502092050209 | 120 | 0.50217937 | 119.502507499 | 1.00455569 |
| mixed_sink_1 | B | 3808000 | 0.497907949791 | 119 | 1.002193925 | 119.002500142 | 1.502321105 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 19281920,
  "extracted_FE": 19281920,
  "residue": {
    "local_buffers": {
      "mixed_sink_0": {
        "channel": "2e657e3e-f2f7-4cfb-9270-e27408c0f096",
        "checkpoint": 1360,
        "id": "091c2bf3-6fc3-4f1d-9775-37ef690561fd",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "mixed_sink_1": {
        "channel": "2e657e3e-f2f7-4cfb-9270-e27408c0f096",
        "checkpoint": 1360,
        "id": "b3e29c68-cb15-462b-8f95-15d73e74faff",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "mixed_source_0": {
        "channel": "2e657e3e-f2f7-4cfb-9270-e27408c0f096",
        "checkpoint": 2720,
        "id": "70427d3c-f891-4f39-af5e-6071d2c24b24",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 0.08958874800009653
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [1147.900949019, 1147.9030246719994] | [1267.9850301889965, 1267.9870831000007] |
| B | [1147.903097120994, 1147.904579049995] | [1267.987256430999, 1267.9891187199974] |
| C | [1147.9046399520012, 1147.9067542729972] | [1267.9891965569986, 1267.9908956149957] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": 1.24502,
        "p95": 3.501207,
        "p99": 6.181039,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1267.9850301889965,
          1267.9870831000007
        ]
      },
      "start": {
        "p50": 1.256181,
        "p95": 4.880527,
        "p99": 19.552175,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1147.900949019,
          1147.9030246719994
        ]
      }
    },
    "B": {
      "end": {
        "p50": 1.257848,
        "p95": 3.602147,
        "p99": 6.617249,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1267.987256430999,
          1267.9891187199974
        ]
      },
      "start": {
        "p50": 1.249506,
        "p95": 3.75679,
        "p99": 8.166358,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1147.903097120994,
          1147.904579049995
        ]
      }
    },
    "C": {
      "end": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          1267.9891965569986,
          1267.9908956149957
        ]
      },
      "start": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          1147.9046399520012,
          1147.9067542729972
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

#### Recorded repeat 3

| Recipient | Server | Steady extracted FE | Output share | Successful pulls | First output s | Last output s | Max pull gap s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| mixed_sink_0 | A | 3840000 | 0.502092050209 | 120 | 0.502765631005 | 119.502387852 | 1.003589491 |
| mixed_sink_1 | B | 3808000 | 0.497907949791 | 119 | 1.002316446 | 119.00484602 | 1.499662345 |

All recorded checks:

```json
{
  "all_steady_sinks_served": true,
  "captured_original_counters_match_driver_delta": true,
  "cumulative_resource_conserved": true,
  "instrumented_cumulative_counters_nondecreasing": true,
  "local_and_SQL_residue_empty_independently": true,
  "low_E2E_bounds_valid": true,
  "low_first_output_lower_ms_quantiles_match": true,
  "low_first_output_upper_ms_quantiles_match": true,
  "low_full_output_lower_ms_quantiles_match": true,
  "low_full_output_upper_ms_quantiles_match": true,
  "low_probe_amounts_conserved": true,
  "low_probe_count_matches_conditions": true,
  "sample_reported_pass": true,
  "steady_all_inputs_fully_accepted": true,
  "steady_fixed_input_attempts": true,
  "steady_input_event_ledger_matches": true,
  "steady_output_event_ledger_matches": true
}
```

Latest cumulative conservation at this repeat (includes earlier repeats on reused channels; do not sum):

```json
{
  "accepted_FE": 28922880,
  "extracted_FE": 28922880,
  "residue": {
    "local_buffers": {
      "mixed_sink_0": {
        "channel": "2e657e3e-f2f7-4cfb-9270-e27408c0f096",
        "checkpoint": 2040,
        "id": "091c2bf3-6fc3-4f1d-9775-37ef690561fd",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "mixed_sink_1": {
        "channel": "2e657e3e-f2f7-4cfb-9270-e27408c0f096",
        "checkpoint": 2040,
        "id": "b3e29c68-cb15-462b-8f95-15d73e74faff",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      },
      "mixed_source_0": {
        "channel": "2e657e3e-f2f7-4cfb-9270-e27408c0f096",
        "checkpoint": 4080,
        "id": "70427d3c-f891-4f39-af5e-6071d2c24b24",
        "pause": "",
        "registered": true,
        "rxFE": 0,
        "rxFluid": 0,
        "rxItem": 0,
        "txFE": 0,
        "txFluid": 0,
        "txItem": 0
      }
    },
    "sql_allocation_remaining_FE": 0,
    "sql_pool_FE": 0
  },
  "seconds": 0.08899095199740259
}
```

This repeat's all-phase event ledger (warmup, steady, low-flow, drain):

```json
{
  "accepted_FE": 9640960,
  "extracted_FE": 9640960
}
```

| Server | First status run-relative interval s | Final status run-relative interval s |
| --- | --- | --- |
| A | [1654.0575214409982, 1654.0588221139988] | [1774.1338957479966, 1774.1359189949944] |
| B | [1654.0588998699968, 1654.061352097] | [1774.1360475979964, 1774.137785867999] |
| C | [1654.0614304650007, 1654.0629852790007] | [1774.1378686419994, 1774.1412157659943] |

WAL ring snapshots (diagnostic only):

```json
{
  "per_server": {
    "A": {
      "end": {
        "p50": 1.136196,
        "p95": 3.552754,
        "p99": 6.822943,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1774.1338957479966,
          1774.1359189949944
        ]
      },
      "start": {
        "p50": 1.153322,
        "p95": 3.480918,
        "p99": 7.309916,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1654.0575214409982,
          1654.0588221139988
        ]
      }
    },
    "B": {
      "end": {
        "p50": 1.26481,
        "p95": 3.602147,
        "p99": 5.812555,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1774.1360475979964,
          1774.137785867999
        ]
      },
      "start": {
        "p50": 1.256048,
        "p95": 3.547977,
        "p99": 6.009921,
        "samples": 2048,
        "status": "INSTRUMENTED_SNAPSHOT",
        "status_run_relative_interval": [
          1654.0588998699968,
          1654.061352097
        ]
      }
    },
    "C": {
      "end": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          1774.1378686419994,
          1774.1412157659943
        ]
      },
      "start": {
        "p50": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "samples": 0,
        "status": "NO_RECORDED_BARRIERS",
        "status_run_relative_interval": [
          1654.0614304650007,
          1654.0629852790007
        ]
      }
    }
  },
  "scope": "Per-JVM last-at-most-2048 completed journal barriers at each status read. Includes file force, atomic move and directory force. Window age is unknown; snapshots may include prior phases. Do not subtract percentiles/sample counts, pool JVM percentiles or call these phase-wide p95 values."
}
```

Recorded per-case error totals (missing measurements remain missing):

```json
{
  "low_flow": {
    "SQL_statement_errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "db_deadlock_retries": {
      "measured_samples": 3,
      "sum": 0
    },
    "errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "quarantined": {
      "measured_samples": 3,
      "sum": 0
    },
    "queue_rejected": {
      "measured_samples": 3,
      "sum": 0
    }
  },
  "steady": {
    "SQL_statement_errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "db_deadlock_retries": {
      "measured_samples": 3,
      "sum": 0
    },
    "errors": {
      "measured_samples": 3,
      "sum": 0
    },
    "quarantined": {
      "measured_samples": 3,
      "sum": 0
    },
    "queue_rejected": {
      "measured_samples": 3,
      "sum": 0
    }
  }
}
```

Final case conservation summary (latest cumulative figures, never sum repeated checkpoints):

```json
{
  "all_phase_event_ledger": {
    "accepted_FE": 28922880,
    "extracted_FE": 28922880
  },
  "do_not_sum_repeats": "Conservation values are cumulative per reused channel, not independent repeat totals.",
  "latest_cumulative_accepted_FE": 28922880,
  "latest_cumulative_extracted_FE": 28922880,
  "latest_cumulative_matches_event_ledger": true
}
```

## Recorded failures, warnings and regression evidence

### baseline

```json
{
  "failures": [],
  "other_live_backend_sessions": [],
  "regressions": [],
  "report_passed": true,
  "status": "passed",
  "warnings": []
}
```

### batch

```json
{
  "failures": [],
  "other_live_backend_sessions": [],
  "regressions": [],
  "report_passed": true,
  "status": "passed",
  "warnings": []
}
```

### fast

```json
{
  "failures": [],
  "other_live_backend_sessions": [],
  "regressions": [],
  "report_passed": true,
  "status": "passed",
  "warnings": []
}
```

## All pairwise comparison metrics and regression flags

```json
[
  {
    "SQL_account_comparison_eligible": true,
    "baseline": "baseline",
    "functional_run_status": "passed",
    "metrics": [
      {
        "baseline": 3440,
        "change_percent": -43.2267441860465,
        "comparison_limitation": null,
        "current": 1953,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_DBtransactions_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 33707,
        "change_percent": -33.33728899041743,
        "comparison_limitation": null,
        "current": 22470,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_SQL_statement_events_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 62399.94782324397,
        "change_percent": 0.4273426107641143,
        "comparison_limitation": null,
        "current": 62666.60938938727,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_actual_extracted_FE_per_second",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 3.0016777080018073,
        "change_percent": -33.31287817281068,
        "comparison_limitation": null,
        "current": 2.0017324699947494,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_max_sink_unserved_seconds",
        "regression": false,
        "scenario": "same",
        "scope": "Median of each repeat's largest gap between actual successful pull events or steady phase boundaries; not measured demand-pending wait time."
      },
      {
        "baseline": 641,
        "change_percent": -6.396255850234011,
        "comparison_limitation": null,
        "current": 600,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_transactions_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 1953,
        "measurement_status": "UNMEASURED",
        "metric": "steady_db_transaction_attempts_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 14834,
        "measurement_status": "UNMEASURED",
        "metric": "steady_db_statements_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_deferred_registry_decodes_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_dropped_wake_hints_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 475,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_exchange_calls_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 7680000,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_input_units_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 7520000,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_output_units_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 406,
        "measurement_status": "UNMEASURED",
        "metric": "steady_batch_devices_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 1200,
        "measurement_status": "UNMEASURED",
        "metric": "steady_batch_records_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_batch_payload_bytes_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_wakes_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 216,
        "measurement_status": "UNMEASURED",
        "metric": "steady_remote_hint_wakes_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 581,
        "measurement_status": "UNMEASURED",
        "metric": "steady_poll_fallback_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 287,
        "measurement_status": "UNMEASURED",
        "metric": "steady_empty_batches_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 151,
        "measurement_status": "UNMEASURED",
        "metric": "steady_allocation_misses_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 128,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_credit_publications_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 622,
        "measurement_status": "UNMEASURED",
        "metric": "steady_wal_writes_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 156454,
        "measurement_status": "UNMEASURED",
        "metric": "steady_wal_bytes_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 12,
        "measurement_status": "UNMEASURED",
        "metric": "steady_wal_identical_skipped_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2829.6383250017243,
        "change_percent": -21.359169780084166,
        "comparison_limitation": null,
        "current": 2225.251071002276,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p50",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2942.9882479998923,
        "change_percent": -20.858711189717948,
        "comparison_limitation": null,
        "current": 2329.1188290022546,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p95",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 3030.4997710009047,
        "change_percent": -23.09248925541053,
        "comparison_limitation": null,
        "current": 2330.68193699728,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p99",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 1.245402,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 4.085739,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 7.281433,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 1.2142185,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 3.445201,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 6.619925,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": 3466,
        "change_percent": -44.806693594922095,
        "comparison_limitation": null,
        "current": 1913,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_DBtransactions_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 33517,
        "change_percent": -36.271145985619235,
        "comparison_limitation": null,
        "current": 21360,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_SQL_statement_events_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 62666.542807812104,
        "change_percent": 8.883156963346295e-05,
        "comparison_limitation": null,
        "current": 62666.59847548571,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_actual_extracted_FE_per_second",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2.5048390699994343,
        "change_percent": -20.06899992186961,
        "comparison_limitation": null,
        "current": 2.0021429189982882,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_max_sink_unserved_seconds",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of each repeat's largest gap between actual successful pull events or steady phase boundaries; not measured demand-pending wait time."
      },
      {
        "baseline": 638,
        "change_percent": -5.0156739811912265,
        "comparison_limitation": null,
        "current": 606,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_transactions_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 1913,
        "measurement_status": "UNMEASURED",
        "metric": "steady_db_transaction_attempts_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 13848,
        "measurement_status": "UNMEASURED",
        "metric": "steady_db_statements_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_deferred_registry_decodes_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_dropped_wake_hints_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 475,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_exchange_calls_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 7680000,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_input_units_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 7520000,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_output_units_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 380,
        "measurement_status": "UNMEASURED",
        "metric": "steady_batch_devices_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 1011,
        "measurement_status": "UNMEASURED",
        "metric": "steady_batch_records_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_batch_payload_bytes_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_wakes_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 305,
        "measurement_status": "UNMEASURED",
        "metric": "steady_remote_hint_wakes_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 548,
        "measurement_status": "UNMEASURED",
        "metric": "steady_poll_fallback_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 331,
        "measurement_status": "UNMEASURED",
        "metric": "steady_empty_batches_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 154,
        "measurement_status": "UNMEASURED",
        "metric": "steady_allocation_misses_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 110,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_credit_publications_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 566,
        "measurement_status": "UNMEASURED",
        "metric": "steady_wal_writes_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 132389,
        "measurement_status": "UNMEASURED",
        "metric": "steady_wal_bytes_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 14,
        "measurement_status": "UNMEASURED",
        "metric": "steady_wal_identical_skipped_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2829.4325420029054,
        "change_percent": -21.295400864285096,
        "comparison_limitation": null,
        "current": 2226.893539998855,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p50",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2943.372719000763,
        "change_percent": -20.769633354841844,
        "comparison_limitation": null,
        "current": 2332.0449969978654,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p95",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2978.4106540028006,
        "change_percent": -18.558377846946648,
        "comparison_limitation": null,
        "current": 2425.665950999246,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p99",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 1.270217,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 4.10364,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 6.91048,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 1.21271,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 3.483219,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 7.159178,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": 3691,
        "change_percent": -44.7575182877269,
        "comparison_limitation": null,
        "current": 2039,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_DBtransactions_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 32560,
        "change_percent": -29.370393120393125,
        "comparison_limitation": null,
        "current": 22997,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_SQL_statement_events_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 63199.94274769974,
        "change_percent": -0.8438709989588955,
        "comparison_limitation": null,
        "current": 62666.61675949327,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_actual_extracted_FE_per_second",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 4.501817197000491,
        "change_percent": 11.070562623730451,
        "comparison_limitation": null,
        "current": 5.000193689000298,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_max_sink_unserved_seconds",
        "regression": true,
        "scenario": "mixed",
        "scope": "Median of each repeat's largest gap between actual successful pull events or steady phase boundaries; not measured demand-pending wait time."
      },
      {
        "baseline": 735,
        "change_percent": 1.7687074829932037,
        "comparison_limitation": null,
        "current": 748,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_transactions_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 2039,
        "measurement_status": "UNMEASURED",
        "metric": "steady_db_transaction_attempts_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 14467,
        "measurement_status": "UNMEASURED",
        "metric": "steady_db_statements_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_deferred_registry_decodes_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_dropped_wake_hints_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 475,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_exchange_calls_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 7680000,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_input_units_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 7520000,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_output_units_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 543,
        "measurement_status": "UNMEASURED",
        "metric": "steady_batch_devices_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 962,
        "measurement_status": "UNMEASURED",
        "metric": "steady_batch_records_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_batch_payload_bytes_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_wakes_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 312,
        "measurement_status": "UNMEASURED",
        "metric": "steady_remote_hint_wakes_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 507,
        "measurement_status": "UNMEASURED",
        "metric": "steady_poll_fallback_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 276,
        "measurement_status": "UNMEASURED",
        "metric": "steady_empty_batches_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 331,
        "measurement_status": "UNMEASURED",
        "metric": "steady_allocation_misses_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 104,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_credit_publications_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 659,
        "measurement_status": "UNMEASURED",
        "metric": "steady_wal_writes_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 117691,
        "measurement_status": "UNMEASURED",
        "metric": "steady_wal_bytes_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 12,
        "measurement_status": "UNMEASURED",
        "metric": "steady_wal_identical_skipped_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2167.576405001455,
        "change_percent": 3.1900841345294584,
        "comparison_limitation": null,
        "current": 2236.7239160012105,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p50",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 3361.8731059978018,
        "change_percent": -30.258720984496613,
        "comparison_limitation": null,
        "current": 2344.613303001097,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p95",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 3579.1117119988485,
        "change_percent": -34.09272023860655,
        "comparison_limitation": null,
        "current": 2358.8951689998794,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p99",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 1.235395,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 3.957421,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 8.760433,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 1.218319,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 3.460392,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 6.882942,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      }
    ],
    "profile": "batch",
    "reason": null,
    "regressions": [
      {
        "baseline": 4.501817197000491,
        "change_percent": 11.070562623730451,
        "comparison_limitation": null,
        "current": 5.000193689000298,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_max_sink_unserved_seconds",
        "regression": true,
        "scenario": "mixed",
        "scope": "Median of each repeat's largest gap between actual successful pull events or steady phase boundaries; not measured demand-pending wait time."
      }
    ],
    "status": "matched"
  },
  {
    "SQL_account_comparison_eligible": true,
    "baseline": "baseline",
    "functional_run_status": "passed",
    "metrics": [
      {
        "baseline": 3440,
        "change_percent": -29.50581395348837,
        "comparison_limitation": null,
        "current": 2425,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_DBtransactions_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 33707,
        "change_percent": -5.693179458272757,
        "comparison_limitation": null,
        "current": 31788,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_SQL_statement_events_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 62399.94782324397,
        "change_percent": 2.1367208454927455,
        "comparison_limitation": null,
        "current": 63733.260515959824,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_actual_extracted_FE_per_second",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 3.0016777080018073,
        "change_percent": -82.95739323927775,
        "comparison_limitation": null,
        "current": 0.5115641279990086,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_max_sink_unserved_seconds",
        "regression": false,
        "scenario": "same",
        "scope": "Median of each repeat's largest gap between actual successful pull events or steady phase boundaries; not measured demand-pending wait time."
      },
      {
        "baseline": 641,
        "change_percent": 24.80499219968799,
        "comparison_limitation": null,
        "current": 800,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_transactions_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 2425,
        "measurement_status": "UNMEASURED",
        "metric": "steady_db_transaction_attempts_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 20822,
        "measurement_status": "UNMEASURED",
        "metric": "steady_db_statements_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_deferred_registry_decodes_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_dropped_wake_hints_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 479,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_exchange_calls_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 7680000,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_input_units_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 7648000,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_output_units_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 800,
        "measurement_status": "UNMEASURED",
        "metric": "steady_batch_devices_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 1360,
        "measurement_status": "UNMEASURED",
        "metric": "steady_batch_records_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_batch_payload_bytes_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 719,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_wakes_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 240,
        "measurement_status": "UNMEASURED",
        "metric": "steady_remote_hint_wakes_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 774,
        "measurement_status": "UNMEASURED",
        "metric": "steady_poll_fallback_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 295,
        "measurement_status": "UNMEASURED",
        "metric": "steady_empty_batches_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 320,
        "measurement_status": "UNMEASURED",
        "metric": "steady_allocation_misses_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 240,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_credit_publications_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 1199,
        "measurement_status": "UNMEASURED",
        "metric": "steady_wal_writes_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 202728,
        "measurement_status": "UNMEASURED",
        "metric": "steady_wal_bytes_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_wal_identical_skipped_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2829.6383250017243,
        "change_percent": -89.22607213405526,
        "comparison_limitation": null,
        "current": 304.86319200281287,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p50",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2942.9882479998923,
        "change_percent": -86.20776096299844,
        "comparison_limitation": null,
        "current": 405.90397399500944,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p95",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 3030.4997710009047,
        "change_percent": -86.45883659433284,
        "comparison_limitation": null,
        "current": 410.36492599960184,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p99",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 1.162677,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 3.340181,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 5.826427,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 1.2614450000000001,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 3.602147,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 6.214902,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": 3466,
        "change_percent": 6.4339296018465,
        "comparison_limitation": null,
        "current": 3689,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_DBtransactions_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 33517,
        "change_percent": 26.93558492705195,
        "comparison_limitation": null,
        "current": 42545,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_SQL_statement_events_fixed_input_count",
        "regression": true,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 62666.542807812104,
        "change_percent": 1.276714116668165,
        "comparison_limitation": null,
        "current": 63466.61540626734,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_actual_extracted_FE_per_second",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2.5048390699994343,
        "change_percent": -60.0691206881302,
        "comparison_limitation": null,
        "current": 1.0002042659980361,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_max_sink_unserved_seconds",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of each repeat's largest gap between actual successful pull events or steady phase boundaries; not measured demand-pending wait time."
      },
      {
        "baseline": 638,
        "change_percent": 120.21943573667713,
        "comparison_limitation": null,
        "current": 1405,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_transactions_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 3689,
        "measurement_status": "UNMEASURED",
        "metric": "steady_db_transaction_attempts_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 27277,
        "measurement_status": "UNMEASURED",
        "metric": "steady_db_statements_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_deferred_registry_decodes_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_dropped_wake_hints_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 478,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_exchange_calls_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 7680000,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_input_units_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 7616000,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_output_units_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 925,
        "measurement_status": "UNMEASURED",
        "metric": "steady_batch_devices_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 1672,
        "measurement_status": "UNMEASURED",
        "metric": "steady_batch_records_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_batch_payload_bytes_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 718,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_wakes_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 717,
        "measurement_status": "UNMEASURED",
        "metric": "steady_remote_hint_wakes_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 538,
        "measurement_status": "UNMEASURED",
        "metric": "steady_poll_fallback_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 534,
        "measurement_status": "UNMEASURED",
        "metric": "steady_empty_batches_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 445,
        "measurement_status": "UNMEASURED",
        "metric": "steady_allocation_misses_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 240,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_credit_publications_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 1404,
        "measurement_status": "UNMEASURED",
        "metric": "steady_wal_writes_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 252852,
        "measurement_status": "UNMEASURED",
        "metric": "steady_wal_bytes_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_wal_identical_skipped_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2829.4325420029054,
        "change_percent": -85.62755202783698,
        "comparison_limitation": null,
        "current": 406.658720006817,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p50",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2943.372719000763,
        "change_percent": -82.68669959101321,
        "comparison_limitation": null,
        "current": 509.5949609967647,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p95",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2978.4106540028006,
        "change_percent": -79.56074857637049,
        "comparison_limitation": null,
        "current": 608.7648419998004,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p99",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 1.154295,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 3.211674,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 6.538404,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 1.251819,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 3.762138,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 8.970729,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": 3691,
        "change_percent": -9.482525060959091,
        "comparison_limitation": null,
        "current": 3341,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_DBtransactions_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 32560,
        "change_percent": 31.05651105651106,
        "comparison_limitation": null,
        "current": 42672,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_SQL_statement_events_fixed_input_count",
        "regression": true,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 63199.94274769974,
        "change_percent": 0.8438657744745948,
        "comparison_limitation": null,
        "current": 63733.265434035115,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_actual_extracted_FE_per_second",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 4.501817197000491,
        "change_percent": -66.68254299621053,
        "comparison_limitation": null,
        "current": 1.499891008999839,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_max_sink_unserved_seconds",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of each repeat's largest gap between actual successful pull events or steady phase boundaries; not measured demand-pending wait time."
      },
      {
        "baseline": 735,
        "change_percent": 92.78911564625851,
        "comparison_limitation": null,
        "current": 1417,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_transactions_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 3341,
        "measurement_status": "UNMEASURED",
        "metric": "steady_db_transaction_attempts_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 26981,
        "measurement_status": "UNMEASURED",
        "metric": "steady_db_statements_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_deferred_registry_decodes_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_dropped_wake_hints_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 479,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_exchange_calls_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 7680000,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_input_units_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 7648000,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_output_units_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 1297,
        "measurement_status": "UNMEASURED",
        "metric": "steady_batch_devices_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 1781,
        "measurement_status": "UNMEASURED",
        "metric": "steady_batch_records_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_batch_payload_bytes_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 719,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_wakes_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 600,
        "measurement_status": "UNMEASURED",
        "metric": "steady_remote_hint_wakes_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 595,
        "measurement_status": "UNMEASURED",
        "metric": "steady_poll_fallback_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 307,
        "measurement_status": "UNMEASURED",
        "metric": "steady_empty_batches_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 818,
        "measurement_status": "UNMEASURED",
        "metric": "steady_allocation_misses_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 240,
        "measurement_status": "UNMEASURED",
        "metric": "steady_local_credit_publications_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 1438,
        "measurement_status": "UNMEASURED",
        "metric": "steady_wal_writes_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 229550,
        "measurement_status": "UNMEASURED",
        "metric": "steady_wal_bytes_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "UNMEASURED",
        "metric": "steady_wal_identical_skipped_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2167.576405001455,
        "change_percent": -90.29153779710977,
        "comparison_limitation": null,
        "current": 210.43833599833306,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p50",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 3361.8731059978018,
        "change_percent": -87.78416590837348,
        "comparison_limitation": null,
        "current": 410.6808409997029,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p95",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 3579.1117119988485,
        "change_percent": -88.32913659566532,
        "comparison_limitation": null,
        "current": 417.7132389959297,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p99",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 1.183416,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 3.552754,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 6.822943,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 1.258651,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 3.602147,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 6.617249,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      }
    ],
    "profile": "fast",
    "reason": null,
    "regressions": [
      {
        "baseline": 33517,
        "change_percent": 26.93558492705195,
        "comparison_limitation": null,
        "current": 42545,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_SQL_statement_events_fixed_input_count",
        "regression": true,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 32560,
        "change_percent": 31.05651105651106,
        "comparison_limitation": null,
        "current": 42672,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_SQL_statement_events_fixed_input_count",
        "regression": true,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      }
    ],
    "status": "matched"
  },
  {
    "SQL_account_comparison_eligible": true,
    "baseline": "batch",
    "functional_run_status": "passed",
    "metrics": [
      {
        "baseline": 1953,
        "change_percent": 24.167946748591906,
        "comparison_limitation": null,
        "current": 2425,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_DBtransactions_fixed_input_count",
        "regression": true,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 22470,
        "change_percent": 41.46862483311082,
        "comparison_limitation": null,
        "current": 31788,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_SQL_statement_events_fixed_input_count",
        "regression": true,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 62666.60938938727,
        "change_percent": 1.7021044172739197,
        "comparison_limitation": null,
        "current": 63733.260515959824,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_actual_extracted_FE_per_second",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2.0017324699947494,
        "change_percent": -74.44393116127299,
        "comparison_limitation": null,
        "current": 0.5115641279990086,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_max_sink_unserved_seconds",
        "regression": false,
        "scenario": "same",
        "scope": "Median of each repeat's largest gap between actual successful pull events or steady phase boundaries; not measured demand-pending wait time."
      },
      {
        "baseline": 600,
        "change_percent": 33.33333333333333,
        "comparison_limitation": null,
        "current": 800,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_transactions_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 1953,
        "change_percent": 24.167946748591906,
        "comparison_limitation": null,
        "current": 2425,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_db_transaction_attempts_fixed_input_count",
        "regression": true,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 14834,
        "change_percent": 40.36672509100714,
        "comparison_limitation": null,
        "current": 20822,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_db_statements_fixed_input_count",
        "regression": true,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 0,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_deferred_registry_decodes_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 0,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_dropped_wake_hints_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 475,
        "change_percent": 0.8421052631578885,
        "comparison_limitation": null,
        "current": 479,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_local_exchange_calls_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 7680000,
        "change_percent": 0.0,
        "comparison_limitation": null,
        "current": 7680000,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_local_input_units_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 7520000,
        "change_percent": 1.7021276595744705,
        "comparison_limitation": null,
        "current": 7648000,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_local_output_units_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 406,
        "change_percent": 97.04433497536947,
        "comparison_limitation": null,
        "current": 800,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_batch_devices_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 1200,
        "change_percent": 13.33333333333333,
        "comparison_limitation": null,
        "current": 1360,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_batch_records_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 0,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_batch_payload_bytes_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 0,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 719,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_local_wakes_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 216,
        "change_percent": 11.111111111111116,
        "comparison_limitation": null,
        "current": 240,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_remote_hint_wakes_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 581,
        "change_percent": 33.218588640275385,
        "comparison_limitation": null,
        "current": 774,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_poll_fallback_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 287,
        "change_percent": 2.7874564459930307,
        "comparison_limitation": null,
        "current": 295,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_empty_batches_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 151,
        "change_percent": 111.92052980132452,
        "comparison_limitation": null,
        "current": 320,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_allocation_misses_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 128,
        "change_percent": 87.5,
        "comparison_limitation": null,
        "current": 240,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_local_credit_publications_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 622,
        "change_percent": 92.7652733118971,
        "comparison_limitation": null,
        "current": 1199,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_wal_writes_fixed_input_count",
        "regression": true,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 156454,
        "change_percent": 29.576744602247306,
        "comparison_limitation": null,
        "current": 202728,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_wal_bytes_fixed_input_count",
        "regression": true,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 12,
        "change_percent": -100.0,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_wal_identical_skipped_fixed_input_count",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2225.251071002276,
        "change_percent": -86.29982944506575,
        "comparison_limitation": null,
        "current": 304.86319200281287,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p50",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2329.1188290022546,
        "change_percent": -82.57263781732897,
        "comparison_limitation": null,
        "current": 405.90397399500944,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p95",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2330.68193699728,
        "change_percent": -82.39292459921438,
        "comparison_limitation": null,
        "current": 410.36492599960184,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p99",
        "regression": false,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 1.245402,
        "change_percent": -6.642433527487501,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 1.162677,
        "measurement_status": "INSTRUMENTED_SNAPSHOT_DIAGNOSTIC",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": 4.085739,
        "change_percent": -18.24781269679733,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 3.340181,
        "measurement_status": "INSTRUMENTED_SNAPSHOT_DIAGNOSTIC",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": 7.281433,
        "change_percent": -19.98241280253489,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 5.826427,
        "measurement_status": "INSTRUMENTED_SNAPSHOT_DIAGNOSTIC",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": 1.2142185,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 1.2614450000000001,
        "measurement_status": "PARTIALLY_MEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": 3.445201,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 3.602147,
        "measurement_status": "PARTIALLY_MEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": 6.619925,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 6.214902,
        "measurement_status": "PARTIALLY_MEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "same",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": 1913,
        "change_percent": 92.83847360167276,
        "comparison_limitation": null,
        "current": 3689,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_DBtransactions_fixed_input_count",
        "regression": true,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 21360,
        "change_percent": 99.1807116104869,
        "comparison_limitation": null,
        "current": 42545,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_SQL_statement_events_fixed_input_count",
        "regression": true,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 62666.59847548571,
        "change_percent": 1.2766241510532517,
        "comparison_limitation": null,
        "current": 63466.61540626734,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_actual_extracted_FE_per_second",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2.0021429189982882,
        "change_percent": -50.04331326664442,
        "comparison_limitation": null,
        "current": 1.0002042659980361,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_max_sink_unserved_seconds",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of each repeat's largest gap between actual successful pull events or steady phase boundaries; not measured demand-pending wait time."
      },
      {
        "baseline": 606,
        "change_percent": 131.84818481848185,
        "comparison_limitation": null,
        "current": 1405,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_transactions_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 1913,
        "change_percent": 92.83847360167276,
        "comparison_limitation": null,
        "current": 3689,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_db_transaction_attempts_fixed_input_count",
        "regression": true,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 13848,
        "change_percent": 96.97429231658002,
        "comparison_limitation": null,
        "current": 27277,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_db_statements_fixed_input_count",
        "regression": true,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 0,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_deferred_registry_decodes_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 0,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_dropped_wake_hints_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 475,
        "change_percent": 0.6315789473684275,
        "comparison_limitation": null,
        "current": 478,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_local_exchange_calls_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 7680000,
        "change_percent": 0.0,
        "comparison_limitation": null,
        "current": 7680000,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_local_input_units_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 7520000,
        "change_percent": 1.2765957446808418,
        "comparison_limitation": null,
        "current": 7616000,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_local_output_units_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 380,
        "change_percent": 143.42105263157893,
        "comparison_limitation": null,
        "current": 925,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_batch_devices_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 1011,
        "change_percent": 65.38081107814044,
        "comparison_limitation": null,
        "current": 1672,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_batch_records_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 0,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_batch_payload_bytes_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 0,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 718,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_local_wakes_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 305,
        "change_percent": 135.08196721311475,
        "comparison_limitation": null,
        "current": 717,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_remote_hint_wakes_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 548,
        "change_percent": -1.8248175182481785,
        "comparison_limitation": null,
        "current": 538,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_poll_fallback_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 331,
        "change_percent": 61.32930513595165,
        "comparison_limitation": null,
        "current": 534,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_empty_batches_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 154,
        "change_percent": 188.96103896103895,
        "comparison_limitation": null,
        "current": 445,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_allocation_misses_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 110,
        "change_percent": 118.18181818181816,
        "comparison_limitation": null,
        "current": 240,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_local_credit_publications_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 566,
        "change_percent": 148.0565371024735,
        "comparison_limitation": null,
        "current": 1404,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_wal_writes_fixed_input_count",
        "regression": true,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 132389,
        "change_percent": 90.99169870608586,
        "comparison_limitation": null,
        "current": 252852,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_wal_bytes_fixed_input_count",
        "regression": true,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 14,
        "change_percent": -100.0,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_wal_identical_skipped_fixed_input_count",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2226.893539998855,
        "change_percent": -81.7387444571317,
        "comparison_limitation": null,
        "current": 406.658720006817,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p50",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2332.0449969978654,
        "change_percent": -78.14815058659732,
        "comparison_limitation": null,
        "current": 509.5949609967647,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p95",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2425.665950999246,
        "change_percent": -74.90318723610639,
        "comparison_limitation": null,
        "current": 608.7648419998004,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p99",
        "regression": false,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 1.270217,
        "change_percent": -9.12615718416616,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 1.154295,
        "measurement_status": "INSTRUMENTED_SNAPSHOT_DIAGNOSTIC",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": 4.10364,
        "change_percent": -21.735970991607456,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 3.211674,
        "measurement_status": "INSTRUMENTED_SNAPSHOT_DIAGNOSTIC",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": 6.91048,
        "change_percent": -5.38422801310473,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 6.538404,
        "measurement_status": "INSTRUMENTED_SNAPSHOT_DIAGNOSTIC",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": 1.21271,
        "change_percent": 3.224925992199301,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 1.251819,
        "measurement_status": "INSTRUMENTED_SNAPSHOT_DIAGNOSTIC",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": 3.483219,
        "change_percent": 8.007506849267877,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 3.762138,
        "measurement_status": "INSTRUMENTED_SNAPSHOT_DIAGNOSTIC",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": 7.159178,
        "change_percent": 25.303896620533827,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 8.970729,
        "measurement_status": "INSTRUMENTED_SNAPSHOT_DIAGNOSTIC",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "cross",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": 2039,
        "change_percent": 63.854830799411474,
        "comparison_limitation": null,
        "current": 3341,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_DBtransactions_fixed_input_count",
        "regression": true,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 22997,
        "change_percent": 85.55463756142106,
        "comparison_limitation": null,
        "current": 42672,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_SQL_statement_events_fixed_input_count",
        "regression": true,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 62666.61675949327,
        "change_percent": 1.7021003042744676,
        "comparison_limitation": null,
        "current": 63733.265434035115,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_actual_extracted_FE_per_second",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 5.000193689000298,
        "change_percent": -70.00334182455008,
        "comparison_limitation": null,
        "current": 1.499891008999839,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_max_sink_unserved_seconds",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of each repeat's largest gap between actual successful pull events or steady phase boundaries; not measured demand-pending wait time."
      },
      {
        "baseline": 748,
        "change_percent": 89.43850267379678,
        "comparison_limitation": null,
        "current": 1417,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_transactions_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2039,
        "change_percent": 63.854830799411474,
        "comparison_limitation": null,
        "current": 3341,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_db_transaction_attempts_fixed_input_count",
        "regression": true,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 14467,
        "change_percent": 86.50031105274071,
        "comparison_limitation": null,
        "current": 26981,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_db_statements_fixed_input_count",
        "regression": true,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 0,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_deferred_registry_decodes_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 0,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_dropped_wake_hints_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 475,
        "change_percent": 0.8421052631578885,
        "comparison_limitation": null,
        "current": 479,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_local_exchange_calls_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 7680000,
        "change_percent": 0.0,
        "comparison_limitation": null,
        "current": 7680000,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_local_input_units_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 7520000,
        "change_percent": 1.7021276595744705,
        "comparison_limitation": null,
        "current": 7648000,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_local_output_units_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 543,
        "change_percent": 138.85819521178635,
        "comparison_limitation": null,
        "current": 1297,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_batch_devices_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 962,
        "change_percent": 85.13513513513513,
        "comparison_limitation": null,
        "current": 1781,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_batch_records_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 0,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_batch_payload_bytes_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 0,
        "change_percent": null,
        "comparison_limitation": null,
        "current": 719,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_local_wakes_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 312,
        "change_percent": 92.3076923076923,
        "comparison_limitation": null,
        "current": 600,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_remote_hint_wakes_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 507,
        "change_percent": 17.357001972386588,
        "comparison_limitation": null,
        "current": 595,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_poll_fallback_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 276,
        "change_percent": 11.231884057971019,
        "comparison_limitation": null,
        "current": 307,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_empty_batches_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 331,
        "change_percent": 147.12990936555892,
        "comparison_limitation": null,
        "current": 818,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_allocation_misses_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 104,
        "change_percent": 130.76923076923075,
        "comparison_limitation": null,
        "current": 240,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_local_credit_publications_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 659,
        "change_percent": 118.20940819423367,
        "comparison_limitation": null,
        "current": 1438,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_wal_writes_fixed_input_count",
        "regression": true,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 117691,
        "change_percent": 95.04465082291765,
        "comparison_limitation": null,
        "current": 229550,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_wal_bytes_fixed_input_count",
        "regression": true,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 12,
        "change_percent": -100.0,
        "comparison_limitation": null,
        "current": 0,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_wal_identical_skipped_fixed_input_count",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2236.7239160012105,
        "change_percent": -90.59167139525417,
        "comparison_limitation": null,
        "current": 210.43833599833306,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p50",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2344.613303001097,
        "change_percent": -82.48406931437124,
        "comparison_limitation": null,
        "current": 410.6808409997029,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p95",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2358.8951689998794,
        "change_percent": -82.29199650389589,
        "comparison_limitation": null,
        "current": 417.7132389959297,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "low_full_output_upper_ms_p99",
        "regression": false,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 1.235395,
        "change_percent": -4.207480198640923,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 1.183416,
        "measurement_status": "INSTRUMENTED_SNAPSHOT_DIAGNOSTIC",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": 3.957421,
        "change_percent": -10.225523137417014,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 3.552754,
        "measurement_status": "INSTRUMENTED_SNAPSHOT_DIAGNOSTIC",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": 8.760433,
        "change_percent": -22.11637255829706,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 6.822943,
        "measurement_status": "INSTRUMENTED_SNAPSHOT_DIAGNOSTIC",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "A"
      },
      {
        "baseline": 1.218319,
        "change_percent": 3.3104630232311916,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 1.258651,
        "measurement_status": "INSTRUMENTED_SNAPSHOT_DIAGNOSTIC",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": 3.460392,
        "change_percent": 4.096501205643754,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 3.602147,
        "measurement_status": "INSTRUMENTED_SNAPSHOT_DIAGNOSTIC",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": 6.882942,
        "change_percent": -3.8601661905621087,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": 6.617249,
        "measurement_status": "INSTRUMENTED_SNAPSHOT_DIAGNOSTIC",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "B"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p50",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p95",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      },
      {
        "baseline": null,
        "change_percent": null,
        "comparison_limitation": "Window age is unknown; ring snapshots can include previous phases, and percentiles cannot be subtracted or pooled across JVMs.",
        "current": null,
        "measurement_status": "UNMEASURED",
        "metric": "WAL_barrier_end_ring_snapshot_ms_p99",
        "regression": false,
        "scenario": "mixed",
        "scope": "Median of repeat-end per-JVM last-at-most-2048 journal barrier percentile snapshots; not a phase-wide percentile.",
        "server": "C"
      }
    ],
    "profile": "fast",
    "reason": null,
    "regressions": [
      {
        "baseline": 1953,
        "change_percent": 24.167946748591906,
        "comparison_limitation": null,
        "current": 2425,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_DBtransactions_fixed_input_count",
        "regression": true,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 22470,
        "change_percent": 41.46862483311082,
        "comparison_limitation": null,
        "current": 31788,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_SQL_statement_events_fixed_input_count",
        "regression": true,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 1953,
        "change_percent": 24.167946748591906,
        "comparison_limitation": null,
        "current": 2425,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_db_transaction_attempts_fixed_input_count",
        "regression": true,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 14834,
        "change_percent": 40.36672509100714,
        "comparison_limitation": null,
        "current": 20822,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_db_statements_fixed_input_count",
        "regression": true,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 622,
        "change_percent": 92.7652733118971,
        "comparison_limitation": null,
        "current": 1199,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_wal_writes_fixed_input_count",
        "regression": true,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 156454,
        "change_percent": 29.576744602247306,
        "comparison_limitation": null,
        "current": 202728,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_wal_bytes_fixed_input_count",
        "regression": true,
        "scenario": "same",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 1913,
        "change_percent": 92.83847360167276,
        "comparison_limitation": null,
        "current": 3689,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_DBtransactions_fixed_input_count",
        "regression": true,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 21360,
        "change_percent": 99.1807116104869,
        "comparison_limitation": null,
        "current": 42545,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_SQL_statement_events_fixed_input_count",
        "regression": true,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 1913,
        "change_percent": 92.83847360167276,
        "comparison_limitation": null,
        "current": 3689,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_db_transaction_attempts_fixed_input_count",
        "regression": true,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 13848,
        "change_percent": 96.97429231658002,
        "comparison_limitation": null,
        "current": 27277,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_db_statements_fixed_input_count",
        "regression": true,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 566,
        "change_percent": 148.0565371024735,
        "comparison_limitation": null,
        "current": 1404,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_wal_writes_fixed_input_count",
        "regression": true,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 132389,
        "change_percent": 90.99169870608586,
        "comparison_limitation": null,
        "current": 252852,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_wal_bytes_fixed_input_count",
        "regression": true,
        "scenario": "cross",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2039,
        "change_percent": 63.854830799411474,
        "comparison_limitation": null,
        "current": 3341,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_DBtransactions_fixed_input_count",
        "regression": true,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 22997,
        "change_percent": 85.55463756142106,
        "comparison_limitation": null,
        "current": 42672,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_SQL_statement_events_fixed_input_count",
        "regression": true,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 2039,
        "change_percent": 63.854830799411474,
        "comparison_limitation": null,
        "current": 3341,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_db_transaction_attempts_fixed_input_count",
        "regression": true,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 14467,
        "change_percent": 86.50031105274071,
        "comparison_limitation": null,
        "current": 26981,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_db_statements_fixed_input_count",
        "regression": true,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 659,
        "change_percent": 118.20940819423367,
        "comparison_limitation": null,
        "current": 1438,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_wal_writes_fixed_input_count",
        "regression": true,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      },
      {
        "baseline": 117691,
        "change_percent": 95.04465082291765,
        "comparison_limitation": null,
        "current": 229550,
        "measurement_status": "MATCHED_FIXED_INPUT_COUNTERS_OR_REPEAT_PERCENTILES",
        "metric": "steady_wal_bytes_fixed_input_count",
        "regression": true,
        "scenario": "mixed",
        "scope": "Three repeat percentiles' median for latency; repeat median for fixed business counters"
      }
    ],
    "status": "matched"
  }
]
```

## Supplied aggregate scope

```json
{
  "RCON_reply_attribution": "MC 1.21.1 DedicatedServer shares one RconConsoleSource output buffer across clients; concurrent commands can cross-contaminate payloads while returning the correct protocol request ID. Prefix, fixed-input and conservation checks retained; the original driver does not preserve complete raw business replies or request-specific body tags.",
  "SQL": "ct_dev account statement/sql events; root observer excluded; other-live-session caveat retained",
  "WAL_barriers": "Per-server ring percentile snapshots are diagnostic and not phase-wide latency. No subtraction or pooling of JVM percentiles; baseline WAL absent.",
  "business": "Fixed source attempts/rounds; all acceptance and output ledger checks retained",
  "conservation": "Latest cumulative per reused channel, not sum of repeat cumulative figures; SQL/WAL/local copies never added",
  "instrumented_counters": "Actual first/final per-server status snapshots supply worker task, batch, Sql-helper and WAL differences. Absent counters are UNMEASURED. local_credit_publications includes cross delivery, so topology/event ledgers must establish source path.",
  "latency": "Actual capability accept -> actual capability pull; lower/upper RCON bounds, not world-save latency",
  "percentiles": "Every repeat retained; aggregate is median of repeat percentiles, not pooled p95",
  "runtime_identity": "An explicit --sequence can bind a completed orchestrator's operator-declared revision to an exact profile child path/SHA. It is not classloader attestation, never overwrites raw git_head, and cannot upgrade functional/resource outcomes. Without it, frozen targets retain the git_head fallback rule.",
  "topology": "Overworld console fixtures may share one chunk. NeighborPump skips neighboring Tesseracts. Different chunks/dimensions/real chests require separate correctness tests.",
  "unmeasured": "No fabricated absent runs, failed-run performance success, phase-wide WAL timing, uncollected early-repeat MC tick means or actual TPS"
}
```
