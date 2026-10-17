#!/usr/bin/env python3
"""Bounded, opt-in MySQL COMMIT response loss for isolated regression fixtures.

By default this script opens no sockets and creates no files. --self-test
uses in-memory packets and temporary filesystem safety checks, without sockets.
Execution is fixed to 127.0.0.1:13307 -> :13306.
Use sslMode=DISABLED, useCompression=false, useServerPrepStmts=false and
autoReconnect=false in the fixture's JDBC URL. This is not a general SQL proxy.

Required control JSON, below the repository's scratch directory, is either
{"schema_version":1,"armed":false} or
{"schema_version":1,"cluster":"dev_example","business_uuid":"<UUID>",
 "phase":"deposit"}. phase may instead be "local". Replace the control file
atomically to arm an already running proxy. One process drops at most one ACK;
changing the control file does not reset this limit.

The target is an exact ct_transfers INSERT with the selected cluster, transfer
UUID and DEPOSIT kind, or the current LOCAL UPDATE with those identifiers. Only
a successful, one-row DML response inside a transaction binds the connection.
The following exact COM_QUERY COMMIT must be fully forwarded before its real
server seq=1 OK is read, validated and deliberately withheld from JDBC. No
prepared EXECUTE is guessed to be COMMIT. Ambiguous or unsupported traffic cannot
produce a successful fault marker. Passwords, complete SQL and payloads are never
logged. Packet hashes are not SQL redaction: only the identified DML/COMMIT and
their OK packets are hashed, never authentication packets.

Example (parents must already exist; the events file must be new):
  python3 scripts/rc_mysql_ack_proxy.py --execute \
    --control scratch/rc/ack-control.json --events logs/rc-ack-unique.jsonl

The independent SELECT proving durable business state, same-ID retry, native
asset extraction and lifecycle assertions belong to the calling test. A captured
OK proves that MySQL acknowledged COMMIT to this proxy, not hardware power-loss
durability, arbitrary COMMIT ambiguity recovery or a complete functional test.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import select
import signal
import socket
import stat
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import uuid


ROOT = Path(__file__).resolve().parents[1]
LISTEN = ("127.0.0.1", 13307)
UPSTREAM = ("127.0.0.1", 13306)
MAX_CONNECTIONS = 16
MAX_PACKET = 2 * 1024 * 1024
MAX_CONTROL = 4096
MAX_LOG_BYTES = 4 * 1024 * 1024
MAX_LOG_EVENTS = 4096
IO_TIMEOUT = 5.0
CLIENT_PROTOCOL_41 = 0x0200
CLIENT_SSL = 0x0800
CLIENT_COMPRESS = 0x0020
CLIENT_ZSTD = 0x04000000
CLIENT_QUERY_ATTRIBUTES = 0x08000000
SERVER_IN_TRANS = 0x0001
QUERY = 0x03
UUID_TEXT = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"


class ProxyError(Exception):
    """Messages are fixed reason codes, never server messages or packet contents."""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Packet:
    sequence: int
    payload: bytes

    def wire(self):
        return len(self.payload).to_bytes(3, "little") + bytes([self.sequence]) + self.payload


class Framer:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        packets = []
        while len(self.buffer) >= 4:
            size = int.from_bytes(self.buffer[:3], "little")
            if size > MAX_PACKET:
                raise ProxyError("packet_limit")
            if len(self.buffer) < size + 4:
                break
            packets.append(Packet(self.buffer[3], bytes(self.buffer[4:size + 4])))
            del self.buffer[:size + 4]
        if len(self.buffer) > MAX_PACKET + 4:
            raise ProxyError("packet_buffer_limit")
        return packets


def lenenc(data, offset):
    if offset >= len(data):
        raise ProxyError("short_ok_packet")
    first = data[offset]
    offset += 1
    if first < 0xFB:
        return first, offset
    sizes = {0xFC: 2, 0xFD: 3, 0xFE: 8}
    size = sizes.get(first)
    if size is None or offset + size > len(data):
        raise ProxyError("invalid_ok_integer")
    return int.from_bytes(data[offset:offset + size], "little"), offset + size


def ok_fields(packet):
    if packet.sequence != 1 or not packet.payload or packet.payload[0] != 0:
        raise ProxyError("not_sequence_one_ok")
    affected, offset = lenenc(packet.payload, 1)
    inserted, offset = lenenc(packet.payload, offset)
    if offset + 4 > len(packet.payload):
        raise ProxyError("short_ok_status")
    status, warnings = struct.unpack_from("<HH", packet.payload, offset)
    return {"affected_rows": affected, "last_insert_id": inserted,
            "status_flags": status, "warnings": warnings}


@dataclass(frozen=True)
class Rule:
    cluster: str
    business_uuid: str
    phase: str

    def metadata(self):
        return {"cluster": self.cluster, "business_uuid": self.business_uuid, "phase": self.phase}

    def fingerprint(self):
        return digest(json.dumps(self.metadata(), sort_keys=True, separators=(",", ":")).encode())


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProxyError("duplicate_control_key")
        result[key] = value
    return result


def parse_control(data):
    if len(data) > MAX_CONTROL:
        raise ProxyError("control_limit")
    try:
        value = json.loads(data, object_pairs_hook=unique_object)
    except (ValueError, UnicodeError):
        raise ProxyError("invalid_control_json") from None
    if not isinstance(value, dict) or set(value) - {"schema_version", "armed", "cluster", "business_uuid", "phase"}:
        raise ProxyError("invalid_control_fields")
    if type(value.get("schema_version", 1)) is not int or value.get("schema_version", 1) != 1:
        raise ProxyError("invalid_control_version")
    if type(value.get("armed", True)) is not bool:
        raise ProxyError("invalid_armed_value")
    if value.get("armed") is False:
        if set(value) - {"schema_version", "armed"}:
            raise ProxyError("disarmed_control_has_target")
        return None
    cluster, business, phase = (value.get(k) for k in ("cluster", "business_uuid", "phase"))
    if not isinstance(cluster, str) or not re.fullmatch(r"(?:dev_|test_)[A-Za-z0-9_.-]{1,60}", cluster) or len(cluster) > 64:
        raise ProxyError("isolated_cluster_required")
    if not isinstance(business, str) or not re.fullmatch(UUID_TEXT, business):
        raise ProxyError("canonical_business_uuid_required")
    if phase not in ("deposit", "local"):
        raise ProxyError("invalid_fault_phase")
    return Rule(cluster, str(uuid.UUID(business)), phase)


def relative_safe_path(path, *, control):
    candidate = Path(path)
    if ".." in candidate.parts:
        raise ProxyError("parent_path_forbidden")
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    try:
        relative = candidate.relative_to(ROOT)
    except ValueError:
        raise ProxyError("path_outside_repository") from None
    allowed = relative.parts[:1] == ("scratch",) if control else (
        relative.parts[:1] in (("scratch",), ("logs",)) or relative.parts[:2] == ("reports", "raw"))
    if not allowed or len(relative.parts) < 2:
        raise ProxyError("path_outside_allowed_directory")
    return relative


@contextmanager
def safe_parent(relative):
    # Directory-relative O_NOFOLLOW on every component also prevents rename/symlink
    # substitution between validation and final open. Existing parents are required.
    if not hasattr(os, "O_NOFOLLOW"):
        raise ProxyError("nofollow_unavailable")
    descriptor = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in relative.parts[:-1]:
            next_descriptor = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        yield descriptor, relative.name
    finally:
        os.close(descriptor)


class ControlFile:
    def __init__(self, path):
        self.relative = relative_safe_path(path, control=True)

    def __call__(self):
        with safe_parent(self.relative) as (parent, name):
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ProxyError("control_not_single_regular_file")
            if metadata.st_size > MAX_CONTROL:
                raise ProxyError("control_limit")
            return parse_control(os.read(descriptor, MAX_CONTROL + 1))
        finally:
            os.close(descriptor)


class JsonlLog:
    def __init__(self, path):
        relative = relative_safe_path(path, control=False)
        with safe_parent(relative) as (parent, name):
            self.descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        self.lock = threading.Lock()
        self.bytes = self.events = 0

    def emit(self, event, *, sync=False, **fields):
        item = {"utc": utc_now(), "monotonic_ns": time.monotonic_ns(), "event": event, **fields}
        data = (json.dumps(item, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
        with self.lock:
            if len(data) > MAX_CONTROL or self.bytes + len(data) > MAX_LOG_BYTES or self.events >= MAX_LOG_EVENTS:
                raise ProxyError("event_log_limit")
            offset = 0
            while offset < len(data):
                written = os.write(self.descriptor, data[offset:])
                if written <= 0:
                    raise ProxyError("short_event_log_write")
                offset += written
            self.bytes += len(data)
            self.events += 1
            if sync:
                os.fsync(self.descriptor)

    def close(self):
        os.close(self.descriptor)


def exact_commit(payload):
    return bool(payload and payload[0] == QUERY and payload[1:].strip().lower() in (b"commit", b"commit;"))


def query_view(payload, attributes):
    """Decode negotiated COM_QUERY framing without changing forwarded wire bytes.

    Connector/J 9.x sends parameter_count=0, parameter_set_count=1 even when no
    query attributes are supplied. This prefix belongs to COM_QUERY, not SQL.
    Nonzero attribute sets are deliberately unsupported rather than guessed.
    """
    if not payload or payload[0] != QUERY or not attributes:
        return payload
    count, offset = lenenc(payload, 1)
    sets, offset = lenenc(payload, offset)
    if count != 0 or sets != 1:
        raise ProxyError("nonzero_query_attributes_not_supported")
    return bytes([QUERY]) + payload[offset:]


def sql_value(token):
    token = token.strip()
    if re.fullmatch(r"'[A-Za-z0-9_.:\-]*'", token):
        return token[1:-1]
    if re.fullmatch(r"-?[0-9]+|NULL", token, flags=re.IGNORECASE):
        return token
    raise ProxyError("unsupported_target_sql_value")


def match_mutation(payload, rule):
    if rule is None or not payload or payload[0] != QUERY:
        return False
    try:
        query = payload[1:].decode("ascii").strip()
        if query.endswith(";"):
            query = query[:-1].strip()
    except UnicodeError:
        return False
    if rule.phase == "deposit":
        match = re.fullmatch(r"INSERT(?:\s+IGNORE)?\s+INTO\s+`?ct_transfers`?\s*\(([^()]*)\)\s*VALUES\s*\(([^()]*)\)", query, re.IGNORECASE)
        if not match:
            return False
        columns = [column.strip().strip("`").lower() for column in match[1].split(",")]
        if len(columns) != len(set(columns)) or any(not re.fullmatch(r"[a-z_]+", column) for column in columns):
            return False
        try:
            values = [sql_value(token) for token in match[2].split(",")]
        except ProxyError:
            return False
        row = dict(zip(columns, values))
        return len(columns) == len(values) and row.get("cluster_id") == rule.cluster and row.get("transfer_id", "").lower() == rule.business_uuid and row.get("kind") == "DEPOSIT" and row.get("state") == "COMMITTED"
    match = re.fullmatch(r"UPDATE\s+`?ct_transfers`?\s+SET\s+`?state`?\s*=\s*'LOCAL'\s+WHERE\s+(.+)", query, re.IGNORECASE)
    if not match:
        return False
    row = {}
    state_filter = False
    clauses = re.split(r"\s+AND\s+", match[1], flags=re.IGNORECASE)
    if len(clauses) != 5:
        return False
    for clause in clauses:
        if re.fullmatch(r"`?state`?\s+IN\s*\(\s*'RESERVED'\s*,\s*'LOCAL'\s*\)", clause, re.IGNORECASE):
            state_filter = True
            continue
        equal = re.fullmatch(r"`?(cluster_id|transfer_id|endpoint_id|kind)`?\s*=\s*('[A-Za-z0-9_.:\-]*')", clause, re.IGNORECASE)
        if not equal or equal[1].lower() in row:
            return False
        row[equal[1].lower()] = sql_value(equal[2])
    return (state_filter and row.get("cluster_id") == rule.cluster and row.get("transfer_id", "").lower() == rule.business_uuid
            and row.get("kind") == "ALLOCATE" and bool(re.fullmatch(UUID_TEXT, row.get("endpoint_id", ""))))


class FaultState:
    def __init__(self, read_rule, log):
        self.read_rule = read_rule
        self.log = log
        self.lock = threading.Lock()
        self.claimant = None
        self.executed = False
        self.counters = Counter()
        self.read_errors = set()

    def count(self, name):
        with self.lock:
            self.counters[name] += 1

    def current(self):
        try:
            return self.read_rule()
        except (OSError, ProxyError):
            with self.lock:
                first = "control_read_invalid" not in self.read_errors
                self.read_errors.add("control_read_invalid")
            if first:
                self.log.emit("control_read_invalid", phase="disarmed", fault_executed=False)
            return None

    def claim(self, connection, rule):
        if self.current() != rule:
            return False
        with self.lock:
            if self.executed or self.claimant is not None:
                return False
            self.claimant = (connection, rule)
            return True

    def release(self, connection):
        with self.lock:
            if self.claimant is not None and self.claimant[0] == connection:
                self.claimant = None

    def drop(self, connection, rule):
        with self.lock:
            if self.executed or self.claimant != (connection, rule):
                raise ProxyError("invalid_fault_claim")
            self.executed = True
            self.counters["ack_drops"] += 1
            self.claimant = None

    def summary(self):
        with self.lock:
            return {"fault_executed": self.executed, "counters": dict(self.counters),
                    "independent_SQL_and_asset_verification": "NOT_RUN_BY_PROXY"}


class Session:
    """One owner thread handles both directions; no response/COMMIT shared-state race."""
    def __init__(self, identifier, faults, send_upstream, send_client):
        self.identifier, self.faults = identifier, faults
        self.send_upstream, self.send_client = send_upstream, send_client
        self.server_id = None
        self.greeting = self.client_handshake = self.authenticated = False
        self.query_attributes = False
        self.pending_mutation = None
        self.bound_rule = self.awaiting_commit = None

    def event(self, event, rule=None, **fields):
        self.faults.log.emit(event, connection=self.identifier, server_connection_id=self.server_id,
                             **(rule.metadata() if rule else {}), **fields)

    def client(self, packet):
        if not self.authenticated:
            if not self.greeting:
                raise ProxyError("client_before_greeting")
            if not self.client_handshake:
                if packet.sequence != 1 or len(packet.payload) < 32:
                    raise ProxyError("unsupported_client_handshake")
                flags = int.from_bytes(packet.payload[:4], "little")
                if not flags & CLIENT_PROTOCOL_41 or flags & (CLIENT_SSL | CLIENT_COMPRESS | CLIENT_ZSTD):
                    raise ProxyError("plaintext_uncompressed_protocol41_required")
                self.query_attributes = bool(flags & CLIENT_QUERY_ATTRIBUTES)
                self.client_handshake = True
            self.send_upstream(packet.wire())
            return
        if packet.sequence != 0 or not packet.payload:
            raise ProxyError("unsupported_command_sequence")
        if self.pending_mutation is not None or self.awaiting_commit is not None:
            raise ProxyError("pipelined_commands_not_supported")
        payload = packet.payload
        try:
            decoded = query_view(payload, self.query_attributes)
        except ProxyError:
            self.bound_rule = None
            self.faults.count("query_attribute_headers_not_targeted")
            self.send_upstream(packet.wire())
            return
        if payload[0] in (0x16, 0x17):
            self.faults.count("prepared_commands_not_targeted")
            self.bound_rule = None
        if payload[0] in (0x01, 0x11, 0x1F):
            self.bound_rule = None
        normalized = decoded[1:].strip().lower() if payload[0] == QUERY else b""
        if normalized.startswith(b"rollback") or normalized in (b"begin", b"begin;") or normalized.startswith((b"start transaction", b"set autocommit")):
            self.bound_rule = None
        if exact_commit(decoded):
            self.faults.count("exact_COM_QUERY_commits")
            rule, self.bound_rule = self.bound_rule, None
            claimed = rule is not None and self.faults.claim(self.identifier, rule)
            self.send_upstream(packet.wire())
            if claimed:
                self.awaiting_commit = rule
                self.faults.count("armed_commit_forwards")
                self.event("commit_forwarded", rule, phase_boundary="awaiting_real_server_OK",
                           query_bytes=len(payload), query_sha256=digest(payload), client_OK_bytes_forwarded=0)
            return
        # Never infer COMMIT from EXECUTE, COMMIT WORK, a comment or another table.
        if normalized.startswith(b"commit"):
            self.bound_rule = None
            self.faults.count("unsupported_commit_variants")
        rule = self.faults.current()
        matched = match_mutation(decoded, rule)
        self.send_upstream(packet.wire())
        if matched:
            self.pending_mutation = rule
            self.faults.count("target_mutation_requests")
            self.event("target_mutation_forwarded", rule, query_bytes=len(payload), query_sha256=digest(payload))

    def server(self, packet):
        if not self.greeting:
            if packet.sequence != 0 or not packet.payload or packet.payload[0] != 10:
                raise ProxyError("unsupported_server_greeting")
            end = packet.payload.find(b"\x00", 1, 257)
            if end < 0 or end + 5 > len(packet.payload):
                raise ProxyError("short_server_greeting")
            self.server_id = int.from_bytes(packet.payload[end + 1:end + 5], "little")
            self.greeting = True
            self.event("server_greeting", phase="authentication")
        elif not self.authenticated:
            if packet.payload and packet.payload[0] == 0 and self.client_handshake:
                self.authenticated = True
                self.event("authentication_completed", phase="transparent_relay",
                           query_attributes_negotiated=self.query_attributes)
        elif self.awaiting_commit is not None:
            rule, self.awaiting_commit = self.awaiting_commit, None
            try:
                fields = ok_fields(packet)
                if fields["affected_rows"] != 0 or fields["last_insert_id"] != 0 or fields["status_flags"] & SERVER_IN_TRANS:
                    raise ProxyError("commit_not_completed_OK")
            except ProxyError:
                self.faults.release(self.identifier)
                self.faults.count("commit_responses_not_dropped")
                self.event("commit_response_not_eligible", rule, packet_bytes=len(packet.payload),
                           packet_sha256=digest(packet.wire()), sequence=packet.sequence, fault_executed=False)
            else:
                self.event("real_commit_OK_received", rule, sync=True, sequence=packet.sequence,
                           packet_bytes=len(packet.payload), packet_sha256=digest(packet.wire()),
                           **fields, client_OK_bytes_forwarded=0, fault_executed=False)
                self.faults.drop(self.identifier, rule)
                self.event("commit_OK_dropped", rule, sync=True, sequence=packet.sequence,
                           packet_bytes=len(packet.payload), packet_sha256=digest(packet.wire()),
                           client_OK_bytes_forwarded=0, fault_executed=True, actual_database_outage=False)
                return False  # Caller closes BOTH sockets without forwarding any OK byte.
        elif self.pending_mutation is not None:
            rule, self.pending_mutation = self.pending_mutation, None
            try:
                fields = ok_fields(packet)
                if fields["affected_rows"] != 1 or not fields["status_flags"] & SERVER_IN_TRANS:
                    raise ProxyError("mutation_not_one_row_in_transaction")
            except ProxyError:
                self.bound_rule = None
                self.faults.count("mutation_responses_not_bound")
                self.event("target_mutation_not_bound", rule, sequence=packet.sequence, fault_executed=False)
            else:
                self.bound_rule = rule
                self.faults.count("target_mutations_confirmed")
                self.event("target_mutation_confirmed", rule, **fields, fault_executed=False)
        self.send_client(packet.wire())
        return True


def relay_connection(client, faults, identifier, stop, sockets, sockets_lock, idle_timeout):
    upstream = None
    try:
        client.settimeout(IO_TIMEOUT)
        client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        upstream = socket.create_connection(UPSTREAM, timeout=IO_TIMEOUT)
        with sockets_lock:
            sockets.add(upstream)
        upstream.settimeout(IO_TIMEOUT)
        upstream.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        session = Session(identifier, faults, upstream.sendall, client.sendall)
        framers = {client: Framer(), upstream: Framer()}
        last_io = time.monotonic()
        while not stop.is_set() and time.monotonic() - last_io < idle_timeout:
            readable, _, _ = select.select([client, upstream], [], [], 0.25)
            for source in readable:
                data = source.recv(65536)
                if not data:
                    return
                last_io = time.monotonic()
                for packet in framers[source].feed(data):
                    if source is client:
                        # Synchronous JDBC must have consumed the previous response. A
                        # partial server packet here is ambiguous, never a drop target.
                        if session.authenticated and framers[upstream].buffer:
                            raise ProxyError("pending_server_fragment_before_command")
                        session.client(packet)
                    elif not session.server(packet):
                        return
        faults.count("connection_timeouts_or_shutdowns")
    except (OSError, ProxyError) as error:
        faults.count("connection_errors")
        faults.log.emit("connection_closed", connection=identifier, phase="relay_error",
                        reason=error.args[0] if isinstance(error, ProxyError) else type(error).__name__)
    finally:
        faults.release(identifier)
        for stream in (client, upstream):
            if stream is not None:
                with sockets_lock:
                    sockets.discard(stream)
                try:
                    stream.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                stream.close()


def run_proxy(args):
    read_control = ControlFile(args.control)
    read_control()  # Validate before creating output or opening a listening socket.
    log = JsonlLog(args.events)
    stop, socket_lock = threading.Event(), threading.Lock()
    sockets, threads = set(), []
    slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
    faults = FaultState(read_control, log)
    old_handlers = {}
    listener = None
    failure = None
    try:
        for number in (signal.SIGINT, signal.SIGTERM):
            old_handlers[number] = signal.signal(number, lambda *_: stop.set())
        log.emit("proxy_start", phase="loopback_only", listen_port=LISTEN[1], upstream_port=UPSTREAM[1],
                 script_sha256=digest(Path(__file__).read_bytes()), max_connections=MAX_CONNECTIONS,
                 max_packet_bytes=MAX_PACKET, fault_executed=False)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(LISTEN)
        listener.listen(MAX_CONNECTIONS)
        listener.settimeout(0.25)
        print(json.dumps({"mode": "EXECUTING", "listen": LISTEN, "upstream": UPSTREAM,
                          "independent_SQL_and_asset_verification": "NOT_RUN_BY_PROXY"}), flush=True)
        deadline = time.monotonic() + args.seconds
        identifier = 0
        while not stop.is_set() and time.monotonic() < deadline:
            try:
                client, _ = listener.accept()
            except socket.timeout:
                continue
            identifier += 1
            if not slots.acquire(blocking=False):
                client.close()
                faults.count("connection_limit_rejections")
                log.emit("connection_rejected", connection=identifier, phase="connection_limit")
                continue
            faults.count("connections_admitted")
            with socket_lock:
                sockets.add(client)
            def worker(accepted=client, number=identifier):
                try:
                    relay_connection(accepted, faults, number, stop, sockets, socket_lock, args.idle_timeout)
                except Exception:
                    faults.count("proxy_worker_failures")
                    stop.set()
                finally:
                    slots.release()
            thread = threading.Thread(target=worker, name=f"rc-ack-proxy-{identifier}", daemon=True)
            thread.start()
            threads = [running for running in threads if running.is_alive()]
            threads.append(thread)
    except (OSError, ProxyError) as error:
        failure = error.args[0] if isinstance(error, ProxyError) else type(error).__name__
    finally:
        stop.set()
        if listener is not None:
            listener.close()
        with socket_lock:
            for stream in list(sockets):
                try:
                    stream.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        deadline = time.monotonic() + IO_TIMEOUT + 1
        for thread in threads:
            thread.join(max(0, deadline - time.monotonic()))
        summary = faults.summary()
        if any(thread.is_alive() for thread in threads):
            failure = failure or "worker_shutdown_timeout"
        if summary["counters"].get("proxy_worker_failures"):
            failure = failure or "proxy_worker_failure"
        summary.update({"mode": "EXECUTED", "state": "FAILED_PROXY" if failure else (
            "ACK_DROPPED" if summary["fault_executed"] else "NOT_EXECUTED"), "failure": failure})
        try:
            log.emit("proxy_stop", phase="finished", sync=True, **summary)
        finally:
            log.close()
            for number, handler in old_handlers.items():
                signal.signal(number, handler)
        print(json.dumps(summary, sort_keys=True), flush=True)
    return 1 if failure else (0 if summary["fault_executed"] else 3)


def self_test():
    class MemoryLog:
        def __init__(self): self.events = []
        def emit(self, event, **fields): self.events.append({"event": event, **fields})

    class Tests(unittest.TestCase):
        business = "01234567-89ab-cdef-0123-456789abcdef"
        endpoint = "11111111-2222-3333-4444-555555555555"

        def rule(self, phase="deposit"):
            return Rule("test_ack", self.business, phase)

        def query(self, phase="deposit"):
            if phase == "deposit":
                sql = f"INSERT INTO ct_transfers(cluster_id,transfer_id,endpoint_id,channel_id,resource_id,amount,kind,state,epoch,remaining) VALUES('test_ack','{self.business}','{self.endpoint}','{self.endpoint}','{self.endpoint}',128,'DEPOSIT','COMMITTED',1,0)"
            else:
                sql = f"UPDATE ct_transfers SET state='LOCAL' WHERE cluster_id='test_ack' AND transfer_id='{self.business}' AND endpoint_id='{self.endpoint}' AND kind='ALLOCATE' AND state IN ('RESERVED','LOCAL')"
            return bytes([QUERY]) + sql.encode()

        def ok(self, *, affected=0, status=0, sequence=1):
            return Packet(sequence, bytes([0, affected, 0]) + struct.pack("<HH", status, 0))

        def fixture(self, phase="deposit"):
            log = MemoryLog()
            faults = FaultState(lambda: self.rule(phase), log)
            upstream, client = [], []
            session = Session(1, faults, upstream.append, client.append)
            session.greeting = session.client_handshake = session.authenticated = True
            return session, faults, log, upstream, client

        def bind(self, session, phase="deposit"):
            session.client(Packet(0, self.query(phase)))
            self.assertTrue(session.server(self.ok(affected=1, status=SERVER_IN_TRANS)))
            self.assertIsNotNone(session.bound_rule)

        def test_tcp_fragmentation_and_multiple_packets(self):
            packets = [Packet(0, b"\x03commit"), self.ok(), Packet(254, b"payload")]
            framer, observed = Framer(), []
            for byte in b"".join(packet.wire() for packet in packets):
                observed.extend(framer.feed(bytes([byte])))
            self.assertEqual(packets, observed)
            self.assertEqual([], Framer().feed(b"\x07\x00"))
            self.assertEqual(packets, Framer().feed(b"".join(p.wire() for p in packets)))

        def test_packet_bound_rejects_header_before_allocating_body(self):
            with self.assertRaises(ProxyError):
                Framer().feed((MAX_PACKET + 1).to_bytes(3, "little") + b"\x00")

        def test_rules_and_duplicate_keys_fail_closed(self):
            data = json.dumps(self.rule().metadata()).encode()
            self.assertEqual(self.rule(), parse_control(data))
            self.assertIsNone(parse_control(b'{"schema_version":1,"armed":false}'))
            for bad in [data.replace(b"test_ack", b"production"), data[:-1], b'[]',
                        b'{"armed":false,"armed":false}', b'{"armed":false,"phase":"local"}',
                        b'{"armed":0}', b" " * (MAX_CONTROL + 1)]:
                with self.subTest(bad_length=len(bad)), self.assertRaises(ProxyError):
                    parse_control(bad)

        def test_path_escape_and_output_scope(self):
            for path in ["scratch/../logs/control.json", "/tmp/control.json", "logs/control.json"]:
                with self.assertRaises(ProxyError): relative_safe_path(path, control=True)
            with self.assertRaises(ProxyError): relative_safe_path("docs/output.jsonl", control=False)
            self.assertEqual(Path("scratch/rc/control.json"), relative_safe_path("scratch/rc/control.json", control=True))

        def test_symlinks_hardlinks_and_existing_output_are_rejected(self):
            global ROOT
            previous = ROOT
            try:
                with tempfile.TemporaryDirectory(prefix="rc-ack-offline-") as temporary:
                    ROOT = Path(temporary)
                    (ROOT / "scratch" / "real").mkdir(parents=True)
                    (ROOT / "logs").mkdir()
                    control = ROOT / "scratch" / "real" / "control.json"
                    control.write_bytes(json.dumps(self.rule().metadata()).encode())
                    self.assertEqual(self.rule(), ControlFile("scratch/real/control.json")())
                    (ROOT / "scratch" / "alias").symlink_to(ROOT / "scratch" / "real", target_is_directory=True)
                    with self.assertRaises(OSError): ControlFile("scratch/alias/control.json")()
                    (ROOT / "scratch" / "control-link.json").symlink_to(control)
                    with self.assertRaises(OSError): ControlFile("scratch/control-link.json")()
                    os.link(control, ROOT / "scratch" / "hard-link.json")
                    with self.assertRaises(ProxyError): ControlFile("scratch/hard-link.json")()
                    (ROOT / "scratch" / "hard-link.json").unlink()
                    control.write_bytes(b"x" * (MAX_CONTROL + 1))
                    with self.assertRaises(ProxyError): ControlFile("scratch/real/control.json")()
                    log = JsonlLog("logs/new.jsonl")
                    log.emit("offline_safety_check", phase="offline")
                    log.close()
                    original = (ROOT / "logs" / "new.jsonl").read_bytes()
                    with self.assertRaises(FileExistsError): JsonlLog("logs/new.jsonl")
                    self.assertEqual(original, (ROOT / "logs" / "new.jsonl").read_bytes())
                    (ROOT / "logs" / "alias.jsonl").symlink_to(control)
                    with self.assertRaises(FileExistsError): JsonlLog("logs/alias.jsonl")
            finally:
                ROOT = previous

        def test_event_log_limits_do_not_write_beyond_bounds(self):
            global ROOT
            previous = ROOT
            try:
                with tempfile.TemporaryDirectory(prefix="rc-ack-log-offline-") as temporary:
                    ROOT = Path(temporary)
                    (ROOT / "logs").mkdir()
                    log = JsonlLog("logs/bounded.jsonl")
                    try:
                        log.bytes = MAX_LOG_BYTES
                        with self.assertRaises(ProxyError): log.emit("too_many_bytes")
                        log.bytes, log.events = 0, MAX_LOG_EVENTS
                        with self.assertRaises(ProxyError): log.emit("too_many_events")
                        self.assertEqual(b"", (ROOT / "logs" / "bounded.jsonl").read_bytes())
                    finally:
                        log.close()
            finally:
                ROOT = previous

        def test_default_mode_cannot_open_sockets(self):
            with mock.patch.object(socket, "socket", side_effect=AssertionError("offline socket forbidden")):
                with mock.patch("sys.stdout", new=io.StringIO()) as output:
                    self.assertEqual(0, main([]))
                self.assertEqual("OFFLINE", json.loads(output.getvalue())["mode"])

        def test_exact_mutations_require_table_cluster_business_and_kind(self):
            for phase in ("deposit", "local"):
                good = self.query(phase)
                self.assertTrue(match_mutation(good, self.rule(phase)))
                for bad in [good.replace(b"test_ack", b"test_other"), good.replace(self.business.encode(), self.endpoint.encode()),
                            good.replace(b"ct_transfers", b"other_table"), b"\x17" + good[1:],
                            b"\x03SELECT 'ct_transfers DEPOSIT test_ack " + self.business.encode() + b"'",
                            good + b"; SELECT 1", good.replace(b"'DEPOSIT'", b"'ALLOCATE'") if phase == "deposit" else good.replace(b"'LOCAL' WHERE", b"'RESERVED' WHERE")]:
                    self.assertFalse(match_mutation(bad, self.rule(phase)))

        def test_only_exact_query_commit(self):
            self.assertTrue(exact_commit(b"\x03 COMMIT; \n"))
            for payload in [b"\x17commit", b"\x03COMMIT WORK", b"\x03/*x*/COMMIT", b"\x03COMMIT; SELECT 1", b""]:
                self.assertFalse(exact_commit(payload))

        def test_connector_j_zero_query_attribute_prefix_is_explicitly_decoded(self):
            self.assertEqual(b"\x03commit", query_view(b"\x03\x00\x01commit", True))
            self.assertFalse(exact_commit(b"\x03\x00\x01commit"))
            self.assertFalse(exact_commit(query_view(b"\x03\x00\x01COMMIT WORK", True)))
            for bad in [b"\x03", b"\x03\x00", b"\x03\x01\x01commit", b"\x03\x00\x02commit"]:
                with self.assertRaises(ProxyError): query_view(bad, True)
            session, faults, _, upstream, client = self.fixture()
            session.query_attributes = True
            request = Packet(0, b"\x03\x00\x01" + self.query()[1:])
            session.client(request)
            self.assertEqual(request.wire(), upstream[-1])
            self.assertTrue(session.server(self.ok(affected=1, status=SERVER_IN_TRANS)))
            commit = Packet(0, b"\x03\x00\x01commit")
            session.client(commit)
            self.assertEqual(commit.wire(), upstream[-1])
            before = len(client)
            self.assertFalse(session.server(self.ok()))
            self.assertEqual(before, len(client))
            self.assertTrue(faults.executed)

        def test_query_attribute_capability_is_read_from_handshake_not_payload_guess(self):
            _, faults, log, _, _ = self.fixture()
            session = Session(7, faults, lambda _: None, lambda _: None)
            session.server(Packet(0, b"\x0a8.4\x00" + (123).to_bytes(4, "little") + b"not_logged"))
            flags = CLIENT_PROTOCOL_41 | CLIENT_QUERY_ATTRIBUTES
            session.client(Packet(1, flags.to_bytes(4, "little") + b"\x00" * 28))
            session.server(Packet(2, b"\x00authentication_OK"))
            self.assertTrue(session.query_attributes)
            ready = [event for event in log.events if event["event"] == "authentication_completed"]
            self.assertTrue(ready[0]["query_attributes_negotiated"])

        def test_real_ok_required_then_all_ack_bytes_withheld(self):
            for phase in ("deposit", "local"):
                session, faults, log, upstream, client = self.fixture(phase)
                self.bind(session, phase)
                before = len(client)
                commit = Packet(0, b"\x03commit")
                session.client(commit)
                self.assertEqual(commit.wire(), upstream[-1])
                self.assertFalse(faults.executed)
                self.assertFalse(session.server(self.ok()))
                self.assertEqual(before, len(client))
                self.assertTrue(faults.executed)
                events = [event["event"] for event in log.events]
                self.assertLess(events.index("commit_forwarded"), events.index("real_commit_OK_received"))
                self.assertLess(events.index("real_commit_OK_received"), events.index("commit_OK_dropped"))

        def test_commit_error_wrong_sequence_and_open_transaction_not_dropped(self):
            for response in [Packet(1, b"\xff\x01\x00#HY000not_logged"), self.ok(sequence=2),
                             self.ok(status=SERVER_IN_TRANS), self.ok(affected=1), Packet(1, b"\x00")]:
                session, faults, _, _, client = self.fixture()
                self.bind(session)
                session.client(Packet(0, b"\x03COMMIT"))
                self.assertTrue(session.server(response))
                self.assertFalse(faults.executed)
                self.assertEqual(response.wire(), client[-1])

        def test_failed_or_autocommit_mutation_cannot_bind(self):
            for response in [self.ok(affected=0, status=SERVER_IN_TRANS), self.ok(affected=1), Packet(1, b"\xffbad")]:
                session, faults, _, _, _ = self.fixture()
                session.client(Packet(0, self.query()))
                session.server(response)
                session.client(Packet(0, b"\x03COMMIT"))
                self.assertTrue(session.server(self.ok()))
                self.assertFalse(faults.executed)

        def test_rollback_prepared_and_commit_variant_disarm(self):
            for payload in [b"\x03ROLLBACK", b"\x03ROLLBACK TO SAVEPOINT x", b"\x17anything", b"\x03COMMIT WORK"]:
                session, faults, _, _, _ = self.fixture()
                self.bind(session)
                session.client(Packet(0, payload))
                session.server(self.ok())
                session.client(Packet(0, b"\x03COMMIT"))
                self.assertTrue(session.server(self.ok()))
                self.assertFalse(faults.executed)

        def test_only_one_fault_across_connections_and_control_rearm(self):
            first, faults, _, _, _ = self.fixture()
            second = Session(2, faults, lambda _: None, lambda _: None)
            second.greeting = second.client_handshake = second.authenticated = True
            self.bind(first)
            self.bind(second)
            first.client(Packet(0, b"\x03COMMIT"))
            second.client(Packet(0, b"\x03COMMIT"))
            self.assertTrue(second.server(self.ok()))
            self.assertFalse(first.server(self.ok()))
            self.bind(second)
            second.client(Packet(0, b"\x03COMMIT"))
            self.assertTrue(second.server(self.ok()))
            self.assertEqual(1, faults.summary()["counters"]["ack_drops"])

        def test_changed_rule_and_pipelining_cannot_drop_wrong_response(self):
            session, faults, _, _, _ = self.fixture()
            self.bind(session)
            faults.read_rule = lambda: None
            session.client(Packet(0, b"\x03COMMIT"))
            self.assertTrue(session.server(self.ok()))
            self.assertFalse(faults.executed)
            session, _, _, _, _ = self.fixture()
            session.client(Packet(0, self.query()))
            with self.assertRaises(ProxyError): session.client(Packet(0, b"\x03COMMIT"))

        def test_tls_compression_and_authentication_never_logged(self):
            for unsupported in (CLIENT_SSL, CLIENT_COMPRESS, CLIENT_ZSTD):
                _, faults, _, _, _ = self.fixture()
                session = Session(2, faults, lambda _: None, lambda _: None)
                session.greeting = True
                with self.assertRaises(ProxyError):
                    session.client(Packet(1, (CLIENT_PROTOCOL_41 | unsupported).to_bytes(4, "little") + b"\x00" * 28))
            _, faults, log, _, _ = self.fixture()
            session = Session(3, faults, lambda _: None, lambda _: None)
            session.server(Packet(0, b"\x0a8.4\x00" + (42).to_bytes(4, "little") + b"not_logged"))
            session.client(Packet(1, CLIENT_PROTOCOL_41.to_bytes(4, "little") + b"\x00" * 28 + b"secret_password_not_logged"))
            session.server(Packet(2, b"\x00authenticated"))
            session.client(Packet(0, b"\x03SELECT 'secret_SQL_payload_not_logged'"))
            text = json.dumps(log.events)
            for secret in ("secret_password_not_logged", "secret_SQL_payload_not_logged", "not_logged"):
                self.assertNotIn(secret, text)

    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    print(json.dumps({"mode": "OFFLINE_SELF_TEST", "tests_run": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors),
                      "network_listen": "NOT_RUN", "real_MySQL_COMMIT_ACK_fault": "NOT_RUN",
                      "native_asset_test": "NOT_RUN"}, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true", help="Explicitly start the fixed loopback proxy.")
    mode.add_argument("--self-test", action="store_true", help="In-memory protocol and temporary-path checks; no sockets or backend.")
    parser.add_argument("--control", help="Existing regular control JSON below repository scratch/; at most 4096 bytes.")
    parser.add_argument("--events", help="NEW JSONL below scratch/, logs/ or reports/raw/; parents must exist.")
    parser.add_argument("--seconds", type=float, default=300.0, help="Bounded execution lifetime, 1..1800 seconds.")
    parser.add_argument("--idle-timeout", type=float, default=60.0, help="Per-connection idle bound, 1..120 seconds.")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.execute:
        print(json.dumps({"mode": "OFFLINE", "network_listen": "NOT_RUN", "real_MySQL_COMMIT_ACK_fault": "NOT_RUN",
                          "instruction": "Use --self-test for offline checks; --execute --control --events is required to listen."}))
        return 0
    if not args.control or not args.events or not 1 <= args.seconds <= 1800 or not 1 <= args.idle_timeout <= 120:
        parser.error("execution requires --control, --events and bounded timeouts")
    try:
        return run_proxy(args)
    except (OSError, ProxyError) as error:
        reason = error.args[0] if isinstance(error, ProxyError) else type(error).__name__
        print(json.dumps({"state": "FAILED_PROXY", "reason": reason, "independent_SQL_and_asset_verification": "NOT_RUN_BY_PROXY"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
