# Vanilla container low-flow supplement

`scripts/optimization-container-benchmark.py` measures real ordinary stone moving
from a newly created vanilla chest into a SEND Tesseract, through the channel, out
of a RECEIVE Tesseract and into another newly created vanilla chest. All machine
I/O is performed by the existing `NeighborPump`. The script never invokes
`push-item` or `pull-item` and adds no item components or packet identifiers.

This is a supplemental low-flow external-container experiment. The matched
original/current runs use two 32-stone probes per layout and a 420-second timeout
after the initial ten-probe original attempt timed out. They do not constitute
the FE benchmark's 30-second warmup/120-second steady measurement, production
factory capacity, or high-volume tail evidence. With only two observations,
nearest-rank p95/p99 equal the observed maximum; report the individual intervals
and maximum, without interpreting these as reliable population tail estimates.
Both matched runs have completed all six probes and passed their independent
resource checks. The current cohort is `68f32db`; see
[the paired report](../reports/optimization-container-comparison-68f32db.md).
The earlier `75392af` comparison remains separate historical evidence below.

## Preparation and execution

Run the supplement as its own sequential stage, without concurrent benchmarks
or RCON sidecars. The script does not launch or stop any server/backend or build
code. Prepare three **new empty** isolated worlds
with distinct server IDs using the established `dev_three_v1`, loopback MySQL and
Redis, and A/B/C RCON ports 25575/25576/25577. The default required world-name prefix
is `world-opt-container-`. Use names such as `world-opt-container-original-A` and
`world-opt-container-current-A` (and B/C). Do not reuse the baseline or B/C worlds.

First run the original `87bf217` frozen launches, then the current frozen native
launches or JAR, with separate new world/server identities. The original A/B/C
launches are under `scratch/dev-launch/461a2a5e6d514b3d8dee60815d06907f`,
`6abe4cc458594e518651384c893118dd`, and `3ebbae306b2a47d1b42860767294a5de`.
Keep those class/resource files unchanged. Their `-Dfml.modFolders` selects frozen
classes even though the general classpath still names shared build directories.

```bash
python3 scripts/optimization-container-benchmark.py --self-test

# After the original frozen servers are ready in new empty container worlds:
python3 scripts/optimization-container-benchmark.py \
  --label container-original2-87bf217 --operator-revision 87bf217 \
  --scenarios same,cross,mixed --probes 2 --timeout 420 \
  --idle 2.2 --poll 0.1 --execute

# Repeat with new frozen 68f32db servers/worlds; the label matches the saved run:
python3 scripts/optimization-container-benchmark.py \
  --label container-current-68f32db-68f32db --operator-revision 68f32db \
  --scenarios same,cross,mixed --probes 2 --timeout 420 \
  --idle 2.2 --poll 0.1 --execute
```

The repository-relative sequential entry is
`scripts/optimization-final-sequence.py`. It runs container, pressure and primary
FE stages in order and manages normal stops and new fixture configuration; it is
not a container-only replay. Run it from the repository root only after the
required prebuilt launch profiles, accepted EULA and isolated backends exist,
all selected test JVMs are stopped, and the exact current source/JAR matches
`reports/optimization-artifact-ready-final.json`.

```bash
# Original launch manifest: JSON object with exactly A/B/C keys and this
# checkout's existing original-frozen runServerA/B/C.sh paths.
python3 scripts/optimization-final-sequence.py --stage original \
  --container-suffix 2 --original-launch-manifest path/to/original-launches.json \
  --execute

# Requires the completed original evidence described below and frozen core68:
python3 scripts/optimization-final-sequence.py --stage current \
  --original-sequence-report reports/optimization-final-sequence-original-68f32db.json --execute
```

Use repository-relative launch paths in the supplied manifest; do not replace
original assets with current classes or assume frozen absolute argfile paths
survive moving a checkout. The original-stage entry writes
`reports/optimization-final-sequence-original-68f32db.json`; current requires an
explicit `--original-sequence-report` and verifies the completed original revision,
unique pressure/primary stages and child SHA-256 values. This measurement used
the earlier complete `reports/optimization-final-sequence-original.json`; that
file passed the same offline checks after fixing the reproduction entry. The
already-running Python module retained its pre-fix implementation; the pre-fix
snapshot/hash is recorded in `reports/optimization-baseline-selection-validation.json`.
No workload or Java classes changed during measurement. Existing sequence
evidence is refused, so these commands are for a separate reproduction with
fresh identities, not an instruction to rerun or overwrite this archive. The
current sequence's later primary stages do not become complete merely because
its container and pressure children passed.

For `optimization-container-benchmark.py`, omitting `--execute` gives an offline
design preview. Its `--self-test` reads
source files and checks the restricted SNBT parser, geometry and timing interval
math; it does not use RCON, SQL, `/proc`, Gradle, or JVMs. A real run reuses the
untouched FE driver's isolation, identity, async channel creation and SQL residue
helpers. Official packaged launches must use the same isolated `run-A/B/C` cwd,
ports and configuration, with explicit `-Dcross_tesseract.testHarness=true` and
`-Dcross_tesseract.config=<repository>/run-A/cross-tesseract.properties` (use the
actual absolute repository path and adjust B/C)
in their actual argv, and exactly one native cross_tesseract JAR in each cwd's
`mods` directory. The unrelated `dev_packaged_v1` smoke fixture is not accepted.

## Geometry and business event

The actual current `ThreeServerHarness` ordinary endpoint expression is
`new BlockPos(x,64,z)`. The script extracts this y=64 from source and records its
hash; y=80 is not used. Each endpoint is at x-offset 4 inside its own chunk; its
chest is on EAST at x+1 in that same chunk. Distinct endpoints are at least 64
blocks apart. Fresh chunks receive vanilla forceload tickets. Before placement,
the script requires air at its exact positions and checks neighboring chest
blocks without reading their inventories. Placement uses `setblock ... keep`.
Only then does it read its own chest's `Items`.

The layouts are A source → A destination (`same`), A → B (`cross`), and A → A+B
(`mixed`). Every probe uses `item replace block ... container.0 with
minecraft:stone 32`. Chest item responses accept only ordinary stone, unique
single-chest slots 0–26, and fixed `Slot`, `id`, `count`/legacy `Count` fields.
Unknown items/components, duplicate slots, and invalid counts abort the run.

Before the next probe, the source chest must be empty, local item/FE/fluid buffers
must each be empty, and SQL balances and allocation remaining must independently
be zero. Completed output must total exactly 32 stones across destination chests.
Two or more guarded observations over at least 2.2 seconds establish the empty
resource state. Only after confirming physical output and those independent zero
checks does the script clear its own confirmed output chests once. A further empty
proof and 2.2-second idle precede the next input. Mixed destinations must both
receive a positive cumulative item count; allocation to both on every probe is
not assumed. SQL allocation remaining and local/WAL copies are never added to
physical chest output or to each other.

## Observation intervals and retained evidence

All observations use one Python monotonic clock and preserve RCON request/reply
intervals. A physical source extraction is bounded by the last source read still
showing 32 stones and the first read showing fewer. Because a read happens inside
its RCON interval, the lower endpoint is the previous request start, not its reply
end. If the first source read already decreased, the conservative earliest bound
is the item-replace request start; this is explicitly marked and does not claim
precise source extraction at input command time.

Destination first increase and full 32-item arrival are likewise bounded by real
chest read intervals. Sequential mixed reads use conservative aggregate frame
bounds and rotate destination read order. A fast transfer can arrive between a
full source read and a destination read; the script retains that first destination
arrival and observes the subsequent source decrease. For source interval `[s0,s1]`
and destination interval `[t0,t1]`, E2E bounds are
`max(0,t0-s1)` through `max(0,t1-s0)`. The output includes both observation span
widths. No cross-JVM `nanoTime`, world-save timestamp, or artificial item identity
is used.

Reports `reports/optimization-container-*.json` retain raw RCON replies, layouts,
each probe's observations and drain proofs, exact chest totals, runtime counters,
PID/world/session/fencing epoch, launch argument-file paths/hashes, and actual
launch-selected class/resource file manifests. Packaged JAR collection retains
the complete JAR hash and embedded class/resource hashes. Standard packaged JAR
resolution is inferred from the actual cwd/mods directory; the old harness has no
class-loader `CodeSource` API. The operator-declared revision and checkout/source
revision are recorded separately. Launch assets are rehashed at the end.

On timeout, unrecognized response, uncertain command result, conservation failure
or runtime error, the script saves the failure and leaves all remaining devices,
chests, items and forceload tickets for diagnosis. It does not clear failure
assets, replay an uncertain mutation, or automatically restart a process. Fully
successful, empty fixtures can be removed.

## Reusing the original frozen launch

`scripts/start-frozen-dev.sh` reuses a named existing launch without running
Gradle or `freeze-dev-launch.py`. Its file-only check requires the launch's own
bounded argument files/classes/resources, Java 21, accepted EULA, and the existing
loopback dev configuration. It reports the selected classes/resources manifest
hashes. Actual launch also holds the same per-server lock as `start-dev.sh` and
rejects another JVM for that requested fixture. The wrapper does not change the
world or server ID: prepare separate new empty container-test worlds/server IDs
before launch, after the main measurements and complete shutdown.

```bash
# File-only validation; no /proc, JVM, backend calls or lock acquisition:
scripts/start-frozen-dev.sh --check A scratch/dev-launch/461a2a5e6d514b3d8dee60815d06907f/runServerA.sh
scripts/start-frozen-dev.sh --check B scratch/dev-launch/6abe4cc458594e518651384c893118dd/runServerB.sh
scripts/start-frozen-dev.sh --check C scratch/dev-launch/3ebbae306b2a47d1b42860767294a5de/runServerC.sh

# Operator only, after the checks and separate fresh-world configuration:
scripts/start-frozen-dev.sh A scratch/dev-launch/461a2a5e6d514b3d8dee60815d06907f/runServerA.sh
# Use the corresponding B/C commands in separate controlled sessions.
```

The original three freezes currently have classes manifest SHA256
`ea3eb2939c924217eb1c0269dce042b82887e72868ea0309fc52bc2a7563b54d`.
This describes the actual selected class files, independently of the current
checkout. `perf` is supported only with its own already-existing
`runServerPerf.sh` and matching saved argument files; no old perf launch is
manufactured by this wrapper. `--check` has been exercised offline for A/B/C;
runtime process/lock guards have not been exercised by this agent.

## Offline review before the physical run

The container observer returns a copy of each command record because the reused
helper removes `reply` while parsing status. The report's original RCON trace
therefore retains that body. Empty-state proofs are registered before reading
SQL/device/chest snapshots, so timeout or failed conservation retains those
snapshots for diagnosis. Successful output is still confirmed before clearing;
uncertain mutations are attempted once and retained without replay.

The shared console response buffer still has no request-specific body nonce.
Use one observer and no simultaneous RCON sidecars for this supplement; saved
request IDs alone do not attest the body. Chest replies must match their exact
coordinates. File manifests identify selected launch assets rather than prove
a JVM class-loader `CodeSource`; their digest recipes are explicitly named, so
different manifest formats must not be compared as identical hashes.

The primary helper's parser now accepts bounded scientific notation such as
`9.72E-4`, rejects partial numeric tokens/non-finite overflow, and retains plain
integer counters above `2**53` as exact integers. This changes parsing and offline
checks only; the original workload/RCON/sleep schedule is unchanged. Historical
A/B/C timing fields excluded by the old parser remain UNMEASURED; the old files
and provenance are not rewritten or backfilled. The old scale parser's truncated
microsecond fields are excluded separately in its failed e405 evidence.

## Initial original attempt and revised supplement scope

The completed initial original report is
`reports/optimization-container-container-original-87bf217-20261006T140734Z-bfcb60.json`
(SHA256 `63fda22a693f8a7cd3468c33fc0d8ec51a4ad42dab71414518a908de28facaae`).
It requested ten probes per layout with a 120-second timeout, and **failed** on
the second `same` probe. The first probe delivered all 32 stones, with actual
source-decrease → full-chest E2E bounds of 4873.477–5083.765 ms, then passed the
independent drain and clear checks. All 1,164 observation frames of the second
probe showed the source chest still holding 32 stones and destination holding
zero. No source-decrease interval exists for that probe, so its E2E is unmeasured;
the timeout must not be converted into a completed 120-second latency. `cross`
and `mixed` were not reached. The report retained the failure fixtures/assets;
its cleared-item count of 32 refers only to the first confirmed output.

The operator traced the original neighbor scan's one-side visit every roughly
two seconds and one of 27 chest slots per visit. Returning to slot 0 across six
sides has a nominal 324-second rotation. This is a source scheduling explanation,
not a measured wait for the failed probe or evidence of channel asset loss.
The subsequent matched original/current runs therefore use new worlds/server IDs,
two probes per layout and a 420-second timeout. They remain separate supplemental
experiments, and their results do not replace or alter the primary nine samples
per mode, 40 FE probes, 30-second warmup or 120-second steady windows. Partial
reports from those subsequent runs are not treated as completed results.

## Completed original two-probe run

The original frozen `87bf217` half completed and passed all six probes on fresh
`world-opt-container-original2-A/B/C` worlds, 2026-10-06 14:18:19.004963–14:41:15.020356
UTC. Its raw report is
`reports/optimization-container-container-original2-87bf217-20261006T141818Z-8488a9.json`
(SHA256 `212c6dc79e00989e48ae43e8d7b475d8fcbba780fc099ef91ea1f25dc2ce600a`).
The current frozen `68f32db` half completed all six probes, 2026-10-06
17:04:40.551709–17:06:30.265434 UTC, on separate new
`world-opt-container-current-68f32db-A/B/C` worlds. Its raw report is
`reports/optimization-container-container-current-68f32db-68f32db-20261006T170440Z-f3e5f6.json`
(SHA256 `c4d88f785dc49c0dace4b309b556015270a9a2438a1045c9a49c3e162777d585`).
Its declared runtime and checkout are both
`68f32db439f445b8f72faf92dc62fbc5b9dce738`; the original runtime remains the
frozen `87bf217`, independently of the original report's checkout label. This
completed physical-container result does not establish completion or performance
of the separate current primary FE stages.

[The original summary](../reports/optimization-container-original2-87bf217-summary.md)
and its [JSON](../reports/optimization-container-original2-87bf217-summary.json) /
[CSV](../reports/optimization-container-original2-87bf217-summary.csv) retain each
probe's input-placement → source-decrease, source-decrease → first/full external
chest, and complete input → full32 intervals. Input-to-source waits were
326.629–326.740 and 315.811–315.922 seconds for same; 6.773–6.885 and
311.062–311.174 seconds for cross; 6.179–6.295 and 309.271–309.393 seconds for
mixed. Source-to-full bounds were 843.273–1057.215 / 2196.591–2416.010 ms for
same, 5167.516–5389.429 / 1332.749–1555.457 ms for cross, and
6863.242–7096.270 / 1695.429–1942.005 ms for mixed. The scanner waits remain
part of the full input-to-arrival observation and must not be hidden by reporting
only the shorter source-to-output interval.

Each probe delivered exactly32 physical stones. Same and cross each delivered64;
mixed's first probe delivered32 to B, its second32 to A, serving each receiver
cumulatively. All21 quiet guards passed, with168 retained snapshots independently
showing zero local buffers, SQL pool and allocation remaining, and the guard's
expected source-empty/destination-zero-or32 chest totals. All192 confirmed stones
were cleared, then the seven empty script-created fixtures were removed. Runtime
error/rejection/quarantine/deadlock-retry deltas were zero. These are sampled
independent guard observations, without an atomic cross-server snapshot claim.

The complete original and the initial failed 10-probe/120-second attempt are
separate cohorts; their raw reports and the derived JSON retain both. The paired
CSV contains the 12 completed original/current probes. The original's scanner
waits, 2.2-second deliberate idle, guarded cleanup and observation uncertainty are
retained. With two probes per layout, any p95/p99 is merely the observed maximum;
the report lists individual intervals and makes no tail-capacity claim.

## Completed 68f32db paired comparison

[The paired report](../reports/optimization-container-comparison-68f32db.md) and
its [JSON](../reports/optimization-container-comparison-68f32db.json) /
[CSV](../reports/optimization-container-comparison-68f32db.csv) retain all 12
individual probes, paired by layout and ordinal. The current input-to-source
observations span conservative bounds of 3.420–6.659 seconds, and source-to-first/
full32 output upper bounds range 208.716–524.523 ms. Full input-to-external-chest
bounds span 3.630–7.079 seconds, including source scanner waiting. Every current
source-to-output upper bound is below its paired original lower bound in these
observations. The worlds and scanner phase were not synchronized; two probes
per layout do not establish population tails or sustained capacity.

| Layout / probe | Current input → source decrease (s) | Current source → first/full32 (ms) | Current full input → external chest32 (s) |
| --- | --- | --- | --- |
| same / 1 | 3.613–3.725 | 103.242–311.740 | 3.822–3.932 |
| same / 2 | 6.411–6.515 | 0.341–208.716 | 6.515–6.620 |
| cross / 1 | 3.420–3.527 | 104.638–316.790 | 3.630–3.738 |
| cross / 2 | 6.450–6.556 | 103.529–314.263 | 6.658–6.765 |
| mixed / 1 | 3.542–3.649 | 0.349–212.654 | 3.648–3.756 |
| mixed / 2 | 6.554–6.659 | 312.668–524.523 | 6.971–7.079 |

Each cohort received and confirmed 192 stones. Both current mixed receivers
received 32 cumulatively; its first probe went to A, its second to B, reversing
the original order. Both cohorts passed 21 quiet guards and retained 168 proof
snapshots each, with independent zero SQL/buffer checks and exact chest counts.
The first positive chest read already showed all32 in every probe, so matching
first/full intervals are observation bounds without an atomic-arrival claim.

Actual two-probe layout DB transaction counts were 5912→154 for same,
3091→162 for cross and 3710→179 for mixed; account SQL events were
41290→1428, 21627→1503 and 27595→1844. These windows include scan waits and
guards, and differ in duration. They do not substitute for the primary fixed
240-input window or its frozen 30% goal. Current WAL writes/bytes were
10/1774, 10/1774 and 11/1997; original WAL/helper/batch fields remain UNMEASURED.
Per-layout counts repeated in CSV probe rows are context and must not be summed.
SQL/WAL mirrors are never added to physical resource totals.

All A/B/C frozen class/resource manifests were rehashed offline and matched their
recorded values. The container JSON bytecode manifests are original
`747021b11bfd2bd3d5c683aa30e633c1fdd3be134e899d0e0b0cff717ecc5540` and current
`1068838aaf3f8f180752c2a078b7dc05600e398a0cbafe77477caacb9aba64ba`;
resource manifests are original
`e668e6b54c3dfe8fea33fad3f29e1c44147b391dc17b3ca474952f50dae5fdea` and current
`2fbf78db6ad3e0c368cbab3760a29a0b90b9acb711f4ff6899d54a4ac2aee668`.
The driver also completed its end PID/session/epoch/asset checks before cleanup;
it retained raw end PID replies but not separate final SQL rows/manifest hashes.
Offline rehash supplies later immutable-file evidence, without claiming a JVM
class-loader `CodeSource` or treating a checkout SHA as loaded runtime proof.

The initial 120-second timeout remains a failed separate cohort. The matched
two-probe supplement does not change the primary 30% per-path transaction goal,
40% same-path p95 reduction, cross-path maximum p95 regression of 20%, or the
separate default 10% descriptive flags. Primary costs end before final
conservation drain; an all-asset conservation pass does not measure tail SQL/WAL
lifecycle cost. No latest primary optimization conclusion is inferred from this
container supplement.

Recompute the archived comparison from the repository root with
`python3 scripts/analysis/compare-container-68f32db.py`. This ROOT-relative recipe
selects the exact completed container children from
`reports/optimization-final-sequence-original.json` and
`reports/optimization-final-sequence-current-68f32db.json`, checks their recorded
raw-report SHA256, and rehashes the selected immutable launch files offline. It
does not contact servers or run a native workload; explicit execution rewrites
only the three derived comparison files.

## Historical 75392af comparison

The earlier frozen `75392af` half completed all six probes, 2026-10-06
15:49:28.376758–15:51:17.319949 UTC, on separate fresh
`world-opt-container-current-A/B/C` worlds. Its raw report is
`reports/optimization-container-container-current-75392af-20261006T154928Z-38ab4f.json`
(SHA256 `d465e1ac20a4c623bc40f1fc6b8fd47bfe8102b1c3441605608d6bcb2e084eb4`).
Its complete [paired Markdown](../reports/optimization-container-comparison-75392af.md),
[JSON](../reports/optimization-container-comparison-75392af.json) and
[CSV](../reports/optimization-container-comparison-75392af.csv) remain unchanged.
That sequence was intentionally stopped after its pressure test before later
primary stages; its container observations are not measurements of `68f32db`.
Neither historical nor current two-probe results establish population p95/p99.
