# RCON observation boundary (offline A/B review)

Observed failure: `2026-10-06T12:01:01.331510+00:00`, server `B`, `tick query` returned `EXTRACTED 0`. The sidecar retained the reply and stopped with `B: ValueError: Unrecognized tick query response; raw reply retained`. Its successful earlier samples remain usable only in their actual windows.

The local 1.21.1 / NeoForge 21.1.252 source shows one shared `DedicatedServer.rconConsoleSource` (lines 70, 98). `runCommand` (554–557) clears that buffer, waits for the main-thread command, then reads it without an atomic block spanning the operation. `RconConsoleSource` (14, 21–38) uses a shared `StringBuffer`. `RconClient` (70, 125–132) wraps the returned string with its own request ID, so the Python `rid == 2` guard cannot prove the body belongs to that command. Independent TCP connections and changing request IDs do not fix the shared output buffer.

This is a source-confirmed mechanism consistent with the recorded wrong reply; the exact thread interleaving was not captured. No packet/header trace was saved.

The FE driver is the only FE writer. Its synchronous push/pull waits for its own main-thread handler, while passive tick/status commands cannot produce ACCEPTED/EXTRACTED markers. Missing markers fail the driver; every 1024-FE probe, fully accepted fixed steady input, event-total ledger, and independently empty SQL/local-buffer check passed in all nine B samples. There is no observed proof of a wrong FE amount or timing. The driver did not retain complete raw business replies or a command-specific body tag, so it cannot independently reconstruct every reply attribution. Preserve the reported E2E bounds with this limitation; the monitor failure does not make all latency false.

Future physical-container supplementation is planned without concurrent RCON sidecars. C is still active: no rerun, repair, live query or workload was performed. Target tickrate is not actual TPS, and these query windows do not establish full-phase or whole-loop MSPT.

Source artifact: `/workspace/build/moddev/artifacts/neoforge-21.1.252-sources.jar`; SHA256 `005619490960aa2e099911bbc562af5cb67505770436a8ed1e63fe14d668e8fc`. [Exact source extracts and failed sample](optimization-rcon-crosstalk-interim-A-B-4cfff0a.json).
