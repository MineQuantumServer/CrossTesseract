#!/usr/bin/env python3
"""Exercise three REAL Minecraft JVMs through console-only dev fixtures and real MySQL.

Requires scripts/dev-backends.sh and runServerA/B/C; refuses non-test clusters.
The synthetic UUIDs here are trusted console fixtures, not an online-player login test.
"""
import concurrent.futures
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid
from rcon import command

ROOT = Path(__file__).resolve().parents[1]
PORTS = [25575, 25576, 25577]
CLUSTER = os.environ.get("CT_TEST_CLUSTER", "dev_three_v1")
if not CLUSTER.startswith(("dev_", "test_")) or not re.fullmatch(r"[a-zA-Z0-9_]+", CLUSTER):
    raise ValueError("Only isolated dev_/test_ clusters are allowed")


def sql(statement):
    env = {k: v for k, v in os.environ.items() if k not in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH")}
    run = subprocess.run(["docker", "--host=unix:///var/run/docker.sock", "exec", "-i", "-e", "MYSQL_PWD=ct_dev_only", "ct-dev-mysql", "mysql", "-u", "ct_dev", "--batch", "--skip-column-names", "cross_tesseract"], input=statement, text=True, capture_output=True, env=env, check=True)
    return [line.split("\t") for line in run.stdout.strip().splitlines() if line]


def poll(read, predicate, seconds=25):
    end = time.monotonic() + seconds
    last = None
    while time.monotonic() < end:
        last = read()
        if predicate(last):
            return last
        time.sleep(.2)
    raise AssertionError(f"timed out; last={last}")


def issue(server, value):
    reply = command(PORTS[server], "ct_test " + value)
    if "ERROR " in reply:
        raise AssertionError(reply)
    return reply


def device(server, x, z):
    text = issue(server, f"inspect {x} {z}")
    match = re.search(r"DEVICE ([\w-]+) registered=(\w+) pause=(.*?) channel=(\S+) (.*)", text)
    if not match:
        raise AssertionError(text)
    result = dict(re.findall(r"(\w+)=(\d+)", match[5]))
    result.update(id=match[1], registered=match[2] == "true", pause=match[3], channel=match[4])
    return {k: int(v) if k.startswith(("tx", "rx")) or k == "checkpoint" else v for k, v in result.items()}


def run():
    checks = []
    for port in PORTS:
        def ready():
            try:
                return command(port,"ct_test status")
            except (ConnectionError,OSError):
                return "starting"
        poll(ready,lambda text: "STATUS online" in text,seconds=40)
    owner, member = str(uuid.uuid4()), str(uuid.uuid4())
    name = "three_" + uuid.uuid4().hex[:10]
    base = int(time.time()) % 2000 + 5000
    locations = [(base, 0), (base + 1, 0), (base + 2, 0)]
    # Test fixtures hold the same chunks loaded as an online player would. These vanilla tickets
    # are independent of the mod's UUID TicketController; they are never used by the implementation.
    for port in PORTS:
        command(port, f"forceload add {base-16} -16 {base+96} 16")
    issue(0, f"create {owner} {name}")
    rows = poll(lambda: sql(f"SELECT channel_id FROM ct_channels WHERE cluster_id='{CLUSTER}' AND name='{name}'"), bool)
    channel = rows[0][0]
    issue(1, f"invite {owner} {channel} {member}")
    invitation = poll(lambda: sql(f"SELECT invite_id FROM ct_invites WHERE cluster_id='{CLUSTER}' AND channel_id='{channel}' AND target_uuid='{member}'"), bool)[0][0]
    issue(2, f"accept {member} {invitation}")
    poll(lambda: sql(f"SELECT player_uuid FROM ct_members WHERE cluster_id='{CLUSTER}' AND channel_id='{channel}'"), lambda r: len(r) == 1)
    checks.append("channel created on A, owner invites through B, offline member accepts through C")
    for i, (x, z) in enumerate(locations):
        issue(i, f"spawn {x} {z} {owner}")
        poll(lambda: device(i, x, z), lambda r: r["registered"])
        issue(i, f"bind {x} {z} {channel}")
        poll(lambda: device(i, x, z), lambda r: r["channel"] == channel and not r["pause"])
        for kind in ("item", "fluid", "fe"):
            issue(i, f"mode {x} {z} cross_tesseract:{kind} {'SEND' if i == 0 else 'RECEIVE'}")
    totals = {"rxFE": 0, "rxItem": 0, "rxFluid": 0}
    for _ in range(6):
        x, z = locations[0]
        for key, value in [("rxFE", f"push-fe {x} {z} 10000"), ("rxItem", f"push-item {x} {z} minecraft:stone 24"), ("rxFluid", f"push-fluid {x} {z} 1000")]:
            reply = issue(0, value)
            accepted = int(re.search(r"ACCEPTED (\d+)", reply)[1])
            totals[key] += accepted
        time.sleep(.9)
    def observed():
        return [device(i, *locations[i]) for i in range(3)]
    result = poll(observed, lambda r: all(sum(d[k] for d in r) == value for k, value in totals.items()) and all(r[0][k.replace("rx", "tx")] == 0 for k in totals))
    assert all(result[i]["rxFE"] > 0 for i in (1, 2)), result
    checks.append("A -> B/C: exact FE/item/fluid conservation and both receivers served; no broadcast copies")
    x, z = locations[1]
    for kind in ("item", "fluid", "fe"):
        issue(1, f"mode {x} {z} cross_tesseract:{kind} BOTH")
    reply = issue(1, f"push-fe {x} {z} 7000")
    totals["rxFE"] += int(re.search(r"ACCEPTED (\d+)", reply)[1])
    reply = issue(0, f"push-fe {locations[0][0]} 0 9000")
    totals["rxFE"] += int(re.search(r"ACCEPTED (\d+)", reply)[1])
    issue(1, f"mode {x} {z} cross_tesseract:fe SEND")
    result = poll(observed, lambda r: sum(d["rxFE"] for d in r) == totals["rxFE"] and r[0]["txFE"] == r[1]["txFE"] == 0)
    checks.append("A/B -> C: concurrent sources add, and existing receive credits are not recycled in BOTH mode")
    for i in (0, 1):
        issue(i, f"chunk-on {locations[i][0]} 0")
    grants = poll(lambda: sql(f"SELECT endpoint_id,state FROM ct_chunk_grants WHERE cluster_id='{CLUSTER}' AND player_uuid='{owner}'"), lambda r: len(r) == 2 and all(x[1] == "ACTIVE" for x in r))
    issue(2, f"chunk-on {locations[2][0]} 0")
    time.sleep(2)
    assert len(sql(f"SELECT endpoint_id FROM ct_chunk_grants WHERE cluster_id='{CLUSTER}' AND player_uuid='{owner}'")) == 2
    checks.append("actual NeoForge tickets on A/B occupy two persistent global slots; C third request refused")
    for i in (0, 1):
        issue(i, f"chunk-off {locations[i][0]} 0")
    poll(lambda: sql(f"SELECT endpoint_id FROM ct_chunk_grants WHERE cluster_id='{CLUSTER}' AND player_uuid='{owner}'"), lambda r: not r)
    with concurrent.futures.ThreadPoolExecutor(3) as executor:
        list(executor.map(lambda i: issue(i, f"chunk-on {locations[i][0]} 0"), range(3)))
    grants = poll(lambda: sql(f"SELECT endpoint_id,state FROM ct_chunk_grants WHERE cluster_id='{CLUSTER}' AND player_uuid='{owner}'"), lambda r: len(r) == 2 and all(x[1] == "ACTIVE" for x in r))
    time.sleep(2)
    assert len(sql(f"SELECT endpoint_id FROM ct_chunk_grants WHERE cluster_id='{CLUSTER}' AND player_uuid='{owner}'")) == 2
    checks.append("three Minecraft JVMs concurrently request same player quota: exactly two ACTIVE grants")
    for i in range(3):
        issue(i, f"chunk-off {locations[i][0]} 0")
    poll(lambda: sql(f"SELECT endpoint_id FROM ct_chunk_grants WHERE cluster_id='{CLUSTER}' AND player_uuid='{owner}'"), lambda r: not r)
    # Other runs may legitimately retain grants. Check our change in tickets.
    baseline_tickets = int(re.search(r'tickets=(\d+)', issue(0, 'status'))[1])
    # Two devices in the SAME chunk, counted separately and independently ticketed.
    sx = base + 32 - ((base + 32) % 16)
    for dx in (1, 2):
        issue(0, f"spawn {sx+dx} 1 {owner}")
        poll(lambda: device(0, sx+dx, 1), lambda r: r["registered"])
        issue(0, f"chunk-on {sx+dx} 1")
    poll(lambda: sql(f"SELECT endpoint_id,state FROM ct_chunk_grants WHERE cluster_id='{CLUSTER}' AND player_uuid='{owner}'"), lambda r: len(r) == 2 and all(x[1] == "ACTIVE" for x in r))
    before = issue(0, "status")
    issue(0, f"chunk-off {sx+1} 1")
    poll(lambda: sql(f"SELECT endpoint_id FROM ct_chunk_grants WHERE cluster_id='{CLUSTER}' AND player_uuid='{owner}'"), lambda r: len(r) == 1)
    after = issue(0, "status")
    assert int(re.search(r'tickets=(\d+)', before)[1]) == baseline_tickets + 2 and int(re.search(r'tickets=(\d+)', after)[1]) == baseline_tickets + 1, (before, after)
    checks.append("same chunk two devices use two slots; closing one leaves the other mod ticket installed")
    issue(0, f"chunk-off {sx+2} 1")
    # Member device is charged to member, never channel owner.
    mx = base + 65
    issue(2, f"spawn {mx} 2 {member}")
    poll(lambda: device(2, mx, 2), lambda r: r["registered"])
    issue(2, f"bind {mx} 2 {channel}")
    poll(lambda: device(2, mx, 2), lambda r: r["channel"] == channel and not r["pause"])
    issue(2, f"mode {mx} 2 cross_tesseract:fe RECEIVE")
    issue(2, f"chunk-on {mx} 2")
    poll(lambda: sql(f"SELECT player_uuid,state FROM ct_chunk_grants WHERE cluster_id='{CLUSTER}' AND player_uuid='{member}'"), lambda r: r == [[member, "ACTIVE"]])
    issue(0, f"remove-member {owner} {channel} {member}")
    poll(lambda: device(2, mx, 2), lambda r: r["pause"] == "forbidden", seconds=8)
    assert "EXTRACTED 0" in issue(2, f"pull-fe {mx} 2 1000")
    checks.append("member device uses member quota; removal disables resource capability within bounded refresh")
    issue(2, f"chunk-off {mx} 2")
    poll(lambda: sql(f"SELECT endpoint_id FROM ct_chunk_grants WHERE cluster_id='{CLUSTER}' AND player_uuid='{member}'"),lambda r:not r)
    report = dict(utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), cluster=CLUSTER, owner=owner, member=member, channel=channel, locations=locations, totals=totals, final_buffers=result, checks=checks, servers=[issue(i, "status") for i in range(3)], scope="three independent Minecraft processes, real backend, console fixtures; online-player GUI not exercised")
    target = ROOT / "reports/three-server.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    for port in PORTS:
        command(port, f"forceload remove {base-16} -16 {base+96} 16")


if __name__ == "__main__":
    run()
