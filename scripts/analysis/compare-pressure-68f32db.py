#!/usr/bin/env python3
"""Offline original87 /68 pressure comparison; reads archived files only.

Actual report names and expected SHA256 come from the matching --label runs
inside the original/current sequence reports. No RCON, SQL, JVM, JFR parsing,
process observation, load generation or modification of raw evidence occurs.
Running writes reports/optimization-pressure-comparison-68f32db.{json,csv,md}.
The current parent sequence may still be running; complete pressure children
are assessed separately from any pending batch/fast stages.
"""
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
SEQUENCES = {
    "original87": ("reports/optimization-final-sequence-original.json", "original-pressure-87bf217"),
    "current68": ("reports/optimization-final-sequence-current-68f32db.json", "current-pressure-68f32db"),
}
OUT = ROOT / "reports/optimization-pressure-comparison-68f32db"


def source(path, data=None):
    data = path.read_bytes() if data is None else data
    return {"path": str(path), "repo_relative_path": path.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def read_saved(path):
    data = path.read_bytes()
    return json.loads(data), source(path, data)


def child_from_sequence(relative, label):
    path = ROOT / relative
    sequence, metadata = read_saved(path)
    matches = []
    for run in sequence.get("runs", []):
        command = run.get("command", [])
        if command.count("--label") == 1 and command.index("--label") + 1 < len(command) and command[command.index("--label") + 1] == label:
            matches.append(run)
    if len(matches) != 1:
        raise ValueError("Requires one exact completed sequence label: " + label)
    run = matches[0]
    relative_report = Path(run.get("report", ""))
    if relative_report.is_absolute() or not relative_report.parts or relative_report.parts[0] != "reports":
        raise ValueError("Sequence report must be a repository-relative reports path")
    report = (ROOT / relative_report).resolve()
    if not report.is_relative_to((ROOT / "reports").resolve()) or report.suffix != ".json":
        raise ValueError("Sequence report escapes archived reports")
    saved, saved_source = read_saved(report)
    if run.get("exit_code") != 0 or not run.get("utc_end") or not saved.get("passed") or saved.get("failures"):
        raise ValueError("Pressure child is not a complete functional pass: " + label)
    if saved_source["sha256"] != run.get("report_sha256"):
        raise ValueError("Recorded sequence SHA differs from actual completed report: " + label)
    pending = [r.get("command") for r in sequence.get("runs", []) if "exit_code" not in r or not r.get("utc_end")]
    if pending or sequence.get("procedure_completed") is False:
        parent_state = "IN_PROGRESS_OR_NOT_COMPLETED_AT_DERIVATION"
    elif sequence.get("passed") is True or sequence.get("procedure_completed") is True:
        parent_state = "PROCEDURE_COMPLETED_CHECK_PERFORMANCE_RESULTS_SEPARATELY"
    else:
        parent_state = "PARENT_STATUS_NOT_PROVEN_COMPLETE"
    return report, saved, saved_source, {"sequence_source": metadata,
        "sequence_snapshot_verbatim": sequence, "completed_pressure_child_verbatim": run,
        "standalone_pressure_child_exit_code": run["exit_code"],
        "parent_state_at_derivation": parent_state, "pending_run_commands": pending,
        "scope": "Sequence snapshot can change as later stages finish. Its current passed=false is not a failed pressure child or a completed primary comparison."}


def source_ledger(events):
    result = {}
    for event in events:
        if event["kind"] != "input":
            continue
        point = result.setdefault(event["endpoint"], {"lane": event["lane"],
            "attempts": 0, "requested_FE": 0, "accepted_FE": 0, "fully_accepted_events": 0})
        point["attempts"] += 1
        point["requested_FE"] += event["requested"]
        point["accepted_FE"] += event["amount"]
        point["fully_accepted_events"] += event["requested"] == event["amount"]
    return result


def change(a, b, direction=0):
    percent = (b / a - 1) * 100 if a is not None and b is not None and a else None
    return {"original": a, "current": b, "change_percent": percent,
        "descriptive_over10percent_regression": percent is not None and direction * percent > 10,
        "scope": "Observed repeat pair/median; default10% descriptive flag, not a statistical confidence test or primary frozen target."}


def med(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def numeric(value, digits=6):
    return "UNMEASURED" if value is None else f"{value:.{digits}f}"


def main():
    helper = ROOT / "scripts/optimization-compare.py"
    spec = importlib.util.spec_from_file_location("offline_pressure_counter_helpers", helper)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    inputs = {name: child_from_sequence(relative, label) for name, (relative, label) in SEQUENCES.items()}
    paths = {name: point[0] for name, point in inputs.items()}
    raw = {name: point[1] for name, point in inputs.items()}
    profiles = {name: m.aggregate_report(name, path) for name, path in paths.items()}
    comparison = m.comparisons(profiles["original87"], profiles["current68"], 10)
    container_path = ROOT / "reports/optimization-container-comparison-68f32db.json"
    container, container_source = read_saved(container_path)
    context_path = ROOT / "reports/optimization-baseline-context.json"
    context, context_source = read_saved(context_path)

    for name, profile in profiles.items():
        if profile["source_sha256"] != inputs[name][2]["sha256"]:
            raise ValueError("Completed raw pressure report changed during aggregation")
        run = inputs[name][3]["completed_pressure_child_verbatim"]
        profile["runtime_revision_declared"] = run["loaded_source_revision_declared"]
        selected = container["cohorts"][name]["identity"]
        identity_matches = all(all(point[key] == selected[server][key] for key in
            ("pid", "server_id", "world_id", "session_id", "fencing_epoch", "argv_sha256"))
            for server, point in raw[name]["identity"].items())
        profile["runtime_provenance_link"] = {"source": container_source,
            "identity_matches_preceding_physical_container_cohort": identity_matches,
            "launch_selected_assets": selected,
            "scope": "Archived PID/session/world/epoch/argv ties the pressure child to preceding container launch manifests; no live lookup/rehash or CodeSource claim here."}
        profile["low_flow_measurement_status"] = "UNMEASURED_PROBES0"
        for case in profile["cases"].values():
            for repeat in case["repeats"]:
                sample = next(s for s in raw[name]["samples"] if s["scenario"] == repeat["scenario"] and s["repeat"] == repeat["repeat"])
                statements = sample["counter_delta"].get("statements")
                detail = {"fixed_window_source_ledger": source_ledger(sample["events"]),
                    "raw_counter_capture_seconds": sample["counter_end"]["end"] - sample["counter_start"]["start"],
                    "SQL_statement_timer_wait_sum_seconds": statements["timer_picoseconds"] / 1e12 if statements else None,
                    "post_counter_final_drain_seconds": sample["conservation"]["seconds"],
                    "cold_channel_sink_service": {name: point for name, point in repeat["sinks"].items() if name.startswith("cold")},
                    "all_receiver_service": repeat["sinks"],
                    "end_timer_snapshots_by_server": {server: {key: value for key, value in point["metrics"].items()
                        if "_ms_" in key or key == "mc_target_ticks_per_second"}
                        for server, point in sample["counter_end"]["servers"].items()},
                    "timer_scope": "Per-server end rings/avg100 snapshots; unknown window age. No pooled/subtracted percentiles, whole-phase MSPT or instantaneous TPS."}
                if repeat["scenario"] == "backpressure":
                    first = next(e for e in sample["events"] if e["kind"] == "output" and e["amount"] > 0)
                    entry = first["end"] - sample["recovery"]["first_actual_output_ms"] / 1000
                    detail.update(backpressure_observed=sample["backpressure_observed"],
                        hold=sample["hold"], held_residue=sample["held_residue"],
                        held_residue_after_quiet=sample["held_residue_after_quiet"],
                        recovery=sample["recovery"], recovery_first_successful_pull=first,
                        recovery_first_output_observation_bounds_ms={
                            "lower": max(0.0, (first["start"] - entry) * 1000),
                            "upper": sample["recovery"]["first_actual_output_ms"]},
                        recovery_first_output_scope="Recovery-entry to successful capability-pull observation interval, reconstructed from raw reply-end delay; held credit extraction, not new-input E2E or an exact mutation timestamp.")
                repeat["pressure_detail"] = detail

    pairs = []
    for scenario, old_case in profiles["original87"]["cases"].items():
        for old in old_case["repeats"]:
            current = next(r for r in profiles["current68"]["cases"][scenario]["repeats"] if r["repeat"] == old["repeat"])
            statements_a, statements_b = old["counter_delta"].get("statements"), current["counter_delta"].get("statements")
            values = {
                "DBtransactions": change(old["counter_delta"]["db_transactions"], current["counter_delta"]["db_transactions"], 1),
                "SQL_statement_events": change(statements_a["events"] if statements_a else None, statements_b["events"] if statements_b else None, 1),
                "SQL_statement_timer_wait_sum_seconds": change(old["pressure_detail"]["SQL_statement_timer_wait_sum_seconds"], current["pressure_detail"]["SQL_statement_timer_wait_sum_seconds"], 1),
                "worker_tasks_distribution": change(old["counter_delta"]["transactions"], current["counter_delta"]["transactions"]),
                "actual_output_FE_per_second": change(old["business"]["actual_extracted_FE_per_second"], current["business"]["actual_extracted_FE_per_second"], -1),
                "max_actual_pull_gap_seconds": change(old["max_sink_unserved_seconds"], current["max_sink_unserved_seconds"], 1),
                "post_counter_drain_seconds": change(old["pressure_detail"]["post_counter_final_drain_seconds"], current["pressure_detail"]["post_counter_final_drain_seconds"], 1)}
            if scenario == "backpressure":
                values["recovery_to_verified_drain_seconds"] = change(old["pressure_detail"]["recovery"]["seconds"], current["pressure_detail"]["recovery"]["seconds"], 1)
            pairs.append({"scenario": scenario, "repeat": old["repeat"], "paired_metrics": values})
    medians = {scenario: {key: change(med(p["paired_metrics"][key]["original"] for p in pairs if p["scenario"] == scenario),
        med(p["paired_metrics"][key]["current"] for p in pairs if p["scenario"] == scenario), direction)
        for key, direction in (("DBtransactions", 1), ("SQL_statement_events", 1),
            ("SQL_statement_timer_wait_sum_seconds", 1), ("worker_tasks_distribution", 0),
            ("actual_output_FE_per_second", -1), ("max_actual_pull_gap_seconds", 1), ("post_counter_drain_seconds", 1))}
        for scenario in profiles["original87"]["cases"]}
    medians["backpressure"]["recovery_to_verified_drain_seconds"] = change(
        med(p["paired_metrics"]["recovery_to_verified_drain_seconds"]["original"] for p in pairs if p["scenario"] == "backpressure"),
        med(p["paired_metrics"]["recovery_to_verified_drain_seconds"]["current"] for p in pairs if p["scenario"] == "backpressure"), 1)
    ledgers = {name: {key: sum(case["conservation"]["all_phase_event_ledger"][key] for case in profile["cases"].values())
        for key in ("accepted_FE", "extracted_FE")} for name, profile in profiles.items()}
    all_service = [{"profile": name, "scenario": repeat["scenario"], "repeat": repeat["repeat"],
        "endpoint": endpoint, "cold_channel": endpoint.startswith("cold"), **point}
        for name, profile in profiles.items() for case in profile["cases"].values()
        for repeat in case["repeats"] for endpoint, point in repeat["sinks"].items()]
    summary = {"schema_version": 1, "report_kind": "offline_pressure_comparison",
        "generated_utc": datetime.now(timezone.utc).isoformat(), "offline_file_derivation_only": True,
        "generator": source(Path(__file__)), "aggregation_helper": source(helper),
        "sources": {name: point[2] for name, point in inputs.items()},
        "sequence_child_provenance": {name: point[3] for name, point in inputs.items()},
        "profiles": profiles, "matched_pressure_comparison": comparison,
        "all_paired_repeats": pairs, "repeat_median_comparisons": medians,
        "all_receiver_service_including_cold_waits": all_service, "all_phase_event_ledgers": ledgers,
        "low_flow_measurement_status": "UNMEASURED_PROBES0_NO_E2E_PERCENTILES",
        "frozen_goals": {"context_source": context_source, "declared_targets": context["frozen_targets"],
            "pressure_assessment": "NOT_APPLICABLE_TO_PRIMARY_GOALS",
            "scope": "30% each same/cross/mixed fixed240-input main-window DB goal,40% same upper-boundp95 reduction,cross upper-boundp95 maximum regression20%; default10% descriptive flags separate. Pressure does not replace primary goals."},
        "limits": {
            "inputs": "Backpressure240x32000FE plus120s no-extraction hold/quiet/recovery. Hotspot240 rounds x7 sources(four hot/three cold)=1680x32000FE. Actual acceptance checked from event returns; every source/receiver preserved.",
            "counter_window": "Backpressure includes recovery/drain before counter_end. Hotspot and normal primary paths counter_end precedes final conservation drain; its tail SQL/WAL is unmeasured, not inferred from conservation or throughput.",
            "assets": "Independent event ledgers/latest per-channel checkpoints, separate zero local/SQL residue checks. Never add SQL allocation/local/WAL mirrors or repeated cumulative checkpoints.",
            "WAL": "Original internal helper/batch/WAL writes/bytes/barriers UNMEASURED. Current actual instrumented counter differences retained without baseline WAL reduction claim.",
            "fairness": "Every receiver's successful pulls, first/last output and maximum observed phase-edge/pull gap preserved, including all cold channels. Backpressure~122s intentional disabled-output interval is not eligible-demand starvation.",
            "latency": "Pressure has0 low-flow probes; no per-packet steady identities/latency percentiles. First recovery reply-end interval concerns held credit, not new-input E2E.",
            "SQL_timer": "ct_dev account SUM_TIMER_WAIT, elapsed summed across statements/workers/attempts, including lock waits and statement-mix changes; not CPU, wall duration, a single-query percentile or full backend-job cost.",
            "observer": "All requested/actual rounds, actual seconds and saturation retained. Given-load FE output and RCON-limited recovery do not establish capacity.",
            "RCON": "One business observer; shared console body lacks request-specific business nonce/full raw per-call bodies in this primary driver. Fixed events/prefix/conservation checks passed; no wrong amount/time demonstrated.",
            "version": "Runtime87 vs exact68 completed pressure children tied to preceding archived container identities/assets. Earlier753/4cfff0a evidence remains historical. Parent68 may be in progress; pressure success does not complete full primary sequence.",
            "metrics": "Native/mod/barrier end-ring/avg100 snapshots lack whole-phase coverage. Credit publications include cross delivery; not same-server-source fast hits. No phase-wide MSPT/TPS claim.",
            "work_performed": "Read archived JSON/source helpers only. No RCON/SQL/JVM/proc/profile or raw-JFR parsing."}}
    summary["complete_valid_standalone_pressure_comparison"] = (
        comparison["status"] == "matched" and len(pairs) == 6 and
        all(p["status"] == "passed" and p["runtime_provenance_link"]["identity_matches_preceding_physical_container_cohort"] for p in profiles.values()) and
        all(point[3]["standalone_pressure_child_exit_code"] == 0 for point in inputs.values()))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    rows = m.table_rows({"profiles": profiles})
    for row in rows:
        repeat = next(r for r in profiles[row["profile"]]["cases"][row["scenario"]]["repeats"] if r["repeat"] == row["repeat"])
        detail = repeat["pressure_detail"]
        row.update(source_report=str(paths[row["profile"]]), source_sha256=inputs[row["profile"]][2]["sha256"],
            business_seconds=repeat["business"]["seconds"], counter_capture_seconds=detail["raw_counter_capture_seconds"],
            scheduled_rounds=repeat["observer"]["scheduled_rounds"], planned_rounds=repeat["observer"]["planned_rounds"],
            late_rounds=repeat["observer"]["late_rounds"], max_lateness_ms=repeat["observer"]["max_lateness_ms"],
            observer_saturated=repeat["observer"]["observer_saturated"], post_counter_drain_seconds=detail["post_counter_final_drain_seconds"],
            tail_FE_after_counter_window=repeat["steady_tail_to_drain_FE"],
            SQL_statement_timer_wait_sum_seconds=detail["SQL_statement_timer_wait_sum_seconds"],
            per_source_ledger_json=json.dumps(detail["fixed_window_source_ledger"]),
            per_sink_service_and_waits_json=json.dumps(repeat["sinks"]),
            cold_channel_service_and_waits_json=json.dumps(detail["cold_channel_sink_service"]),
            final_residue_json=json.dumps(repeat["cumulative_conservation"]["residue"]),
            baseline_WAL_status="UNMEASURED", low_flow_status="UNMEASURED_PROBES0",
            parent_state=inputs[row["profile"]][3]["parent_state_at_derivation"],
            recovery_seconds=detail.get("recovery", {}).get("seconds"),
            first_recovery_output_reply_end_ms=detail.get("recovery", {}).get("first_actual_output_ms"),
            first_recovery_output_lower_ms=detail.get("recovery_first_output_observation_bounds_ms", {}).get("lower"),
            first_recovery_output_upper_ms=detail.get("recovery_first_output_observation_bounds_ms", {}).get("upper"),
            held_residue_json=json.dumps(detail.get("held_residue")),
            held_quiet_residue_json=json.dumps(detail.get("held_residue_after_quiet")))
    with OUT.with_suffix(".csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, list(dict.fromkeys(key for row in rows for key in row)))
        writer.writeheader()
        writer.writerows(rows)

    table = "\n".join(f"| {p['scenario']} /{p['repeat']} | {240 if p['scenario']=='backpressure' else 1680} | "
        f"{p['paired_metrics']['DBtransactions']['original']} → {p['paired_metrics']['DBtransactions']['current']} | "
        f"{p['paired_metrics']['SQL_statement_events']['original']} → {p['paired_metrics']['SQL_statement_events']['current']} | "
        f"{p['paired_metrics']['worker_tasks_distribution']['original']} → {p['paired_metrics']['worker_tasks_distribution']['current']} |"
        for p in pairs)
    median_table = "\n".join(f"| {scenario} /{key} | {numeric(value['original'])} → {numeric(value['current'])} | "
        f"{numeric(value['change_percent'],2)}% | {value['descriptive_over10percent_regression']} |"
        for scenario, values in medians.items() for key, value in values.items())
    service_table = "\n".join(f"| {s['profile']} /{s['scenario']} /{s['repeat']} | {s['endpoint']}({s['server']}) | "
        f"{s['actual_extracted_FE']} | {s['successful_pull_events']} | {s['first_output_seconds']:.6f} | "
        f"{s['last_output_seconds']:.6f} | {s['max_unserved_seconds']:.6f} |" for s in all_service)
    recovery_table = "\n".join(f"| {name} /{repeat['repeat']} | {repeat['pressure_detail']['recovery']['seconds']:.6f} | "
        f"{repeat['pressure_detail']['recovery']['first_actual_output_ms']:.6f} | "
        f"{repeat['pressure_detail']['recovery_first_output_observation_bounds_ms']['lower']:.6f}–"
        f"{repeat['pressure_detail']['recovery_first_output_observation_bounds_ms']['upper']:.6f} |"
        for name, profile in profiles.items() for repeat in profile["cases"]["backpressure"]["repeats"])
    tail_table = "\n".join(f"| {name} /{repeat['repeat']} | {repeat['steady_tail_to_drain_FE']} | "
        f"{repeat['pressure_detail']['post_counter_final_drain_seconds']:.6f} |"
        for name, profile in profiles.items() for repeat in profile["cases"]["hotspot"]["repeats"])
    timer_table = "\n".join(f"| {scenario} | {numeric(values['SQL_statement_timer_wait_sum_seconds']['original'])} → "
        f"{numeric(values['SQL_statement_timer_wait_sum_seconds']['current'])} | "
        f"{numeric(values['SQL_statement_timer_wait_sum_seconds']['change_percent'],2)}% |" for scenario, values in medians.items())
    error_table = "\n".join(f"| {name} /{scenario} /{repeat['repeat']} | {repeat['counter_delta']['db_deadlock_retries']} | "
        f"{(repeat['counter_delta'].get('statements') or {}).get('errors')} | {repeat['counter_delta']['errors']} | "
        f"{repeat['counter_delta']['queue_rejected']} | {repeat['counter_delta']['quarantined']} |"
        for name, profile in profiles.items() for scenario, case in profile["cases"].items() for repeat in case["repeats"])
    source_table = "\n".join(f"| {name} | {point[2]['repo_relative_path']} | {point[2]['sha256']} | "
        f"{point[3]['completed_pressure_child_verbatim']['utc_start']} → {point[3]['completed_pressure_child_verbatim']['utc_end']} | "
        f"{raw[name]['elapsed_seconds']:.6f} |" for name, point in inputs.items())
    md = f"""# Original87 /68f32db pressure evidence

Both standalone children exited0 and functionally passed all six windows. Actual source names and SHA256 were read from the exact completed --label entries in the two sequence reports and verified against the raw files. This does not label pending current B/C or the entire parent sequence completed.

| Cohort | Actual raw file | SHA256 | Parent-recorded child UTC start → end | Raw observer elapsed seconds |
| --- | --- | --- | --- | --- |
{source_table}

Conditions match:30s warmup,120s phase,3 repeats,no low-flow probes. Backpressure supplies240×32000FE with120s intentionally disabled external outputs and then recovery. Hotspot supplies240 rounds×7 sources(four hot/three cold),1680×32000FE. Inputs are counted from actual native acceptance events. All12 observer drive/hold windows retain rounds, lateness and saturation; all expected rounds and accepted quantities passed.

| Case /repeat | Actual source events | DBtx original →68 | ct_dev account SQL events original →68 | Completed worker tasks original →68 |
| --- | --- | --- | --- | --- |
{table}

| Case /repeat-median metric | Original →68 | Change | Default10% descriptive regression |
| --- | --- | --- | --- |
{median_table}

These are repeat medians/individual paired observations, not statistical confidence tests. Worker counts describe scheduled work rather than SQL transactions. All raw driver regressions and independently derived flags remain in JSON. The pressure workload cannot substitute for the frozen primary same/cross/mixed30% DB goal.

| Cohort /case /repeat | Deadlock retries | Account SQL errors | Worker errors | Queue rejections | Quarantines |
| --- | --- | --- | --- | --- | --- |
{error_table}

Original hotspot SQL errors/retries281/191/149,total621, remain visible despite recovery and functional success. No recovered error is removed by comparing only completed outputs.

| Cohort /backpressure repeat | Recovery to verified drain(s) | First output raw reply-end delay(ms) | Conservative recovery-entry→successful-pull interval(ms) |
| --- | --- | --- | --- |
{recovery_table}

First output extracts held credit, not a new source input E2E. The raw delay is a reply-end observation; reconstructed intervals include its command span. Each held pool/local-buffer/allocation-remaining snapshot and the quiet repeat remain in JSON/CSV, separately, without adding mirrors as assets. The~122s maximum successful-pull gap includes the deliberately disabled120s outputs and quiet guard; it does not prove eligible-demand starvation.

All receiver service and waiting observations, including every cold endpoint, follow. First/last times are seconds relative to that sample's phase start. Maximum gap includes phase edges and sampled successful pulls; it is not a per-packet/eligible-demand latency.

| Cohort /case /repeat | Receiver(server) | Actual phase output FE | Successful pulls | First output(s) | Last output(s) | Maximum observed unserved/pull gap(s) |
| --- | --- | --- | --- | --- | --- | --- |
{service_table}

| Cohort /hotspot repeat | FE actually drained after counter_end | Separate final drain(s) |
| --- | --- | --- |
{tail_table}

Backpressure recovery/drain is included before counter_end. Hotspot counter_end occurs before final conservation drain, so post-counter tail SQL/WAL cost is UNMEASURED. Counts/FE throughput inside120s plus full final asset conservation do not establish full-lifecycle cost. Per-server counter capture intervals and actual optional worker/batch/helper/WAL counters are retained; original WAL writes/bytes/barriers remain UNMEASURED, not0, and no baseline WAL reduction is claimed.

| Case | Median account SQL SUM_TIMER_WAIT seconds, original →68 | Change |
| --- | --- | --- |
{timer_table}

SUM_TIMER_WAIT sums server-side elapsed across statements, workers and attempts, including lock waits and different statement mixes. It is not CPU time, full wall duration, single-query latency percentiles or whole backend-job time. The root observer is excluded from ct_dev counts; saved reports have no other live backend sessions.

All-phase independent event ledgers are preserved:original accepted/extracted{ledgers['original87']['accepted_FE']:,}/{ledgers['original87']['extracted_FE']:,}FE,current{ledgers['current68']['accepted_FE']:,}/{ledgers['current68']['extracted_FE']:,}FE. Latest per-channel checkpoint and separate zero SQL/local checks agree. Repeated cumulative checkpoints or mirrored SQL/WAL/local records are never summed. Given-load throughput/recovery is observer-limited evidence, not factory capacity.

Saved PID/server/world/session/epoch/argv match each cohort's preceding completed physical-container identity and selected launch manifests. Runtime87 vs exact68 remains distinct from checkout labels and historical753/4cfff0a evidence. Shared RCON reply bodies lack a business nonce; single observer/fixed events/static conservation checks passed without exact response-interleaving proof or demonstrated wrong FE timing/amount. End native/mod/barrier rings and avg100 snapshots have unknown coverage and are not whole-phase MSPT/TPS/percentiles.

Low-flow E2E is UNMEASURED(probes0). Frozen primary targets remain30% DB reduction per fixed240-input same/cross/mixed window,40% same upper-boundp95 reduction,cross upper-boundp95 regression at most20%; default10% descriptive flags are separate. New B/C primary results are assessed only from their complete reports.

Recompute offline: python3 scripts/analysis/compare-pressure-68f32db.py. This recipe reads sequence snapshots and saved reports only; no live workload/queries/observations or JFR parsing.

[Complete JSON](optimization-pressure-comparison-68f32db.json) · [All12 repeat CSV rows](optimization-pressure-comparison-68f32db.csv)
"""
    OUT.with_suffix(".md").write_text(md)
    print("Saved", *(str(OUT.with_suffix(s)) for s in (".json", ".csv", ".md")))
    print("Complete paired pressure:", summary["complete_valid_standalone_pressure_comparison"],
        "default flags:", comparison["regressions"])
    return 0 if summary["complete_valid_standalone_pressure_comparison"] else 1


if __name__ == "__main__":
    sys.exit(main())
