#!/usr/bin/env python3
"""Small, bounded RCON client for isolated test servers; no external Python packages."""
import argparse
import os
import socket
import struct


def read_exact(sock, size):
    result = bytearray()
    while len(result) < size:
        part = sock.recv(size - len(result))
        if not part:
            raise ConnectionError("RCON closed")
        result.extend(part)
    return bytes(result)


def packet(sock, ident, kind, value):
    data = struct.pack("<ii", ident, kind) + value.encode("utf-8") + b"\0\0"
    sock.sendall(struct.pack("<i", len(data)) + data)
    size = struct.unpack("<i", read_exact(sock, 4))[0]
    if not 10 <= size <= 1_048_576:
        raise ValueError("invalid RCON packet size")
    reply = read_exact(sock, size)
    rid, rkind = struct.unpack("<ii", reply[:8])
    return rid, rkind, reply[8:-2].decode("utf-8")


def command(port, text, password=None, timeout=10):
    password = password or os.environ.get("CT_TEST_RCON_PASSWORD", "ct_dev_rcon_only")
    with socket.create_connection(("127.0.0.1", port), timeout) as sock:
        sock.settimeout(timeout)
        rid, _, _ = packet(sock, 1, 3, password)
        if rid == -1:
            raise PermissionError("RCON authentication rejected")
        rid, _, reply = packet(sock, 2, 2, text)
        if rid != 2:
            raise ValueError("invalid RCON response")
        return reply


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", type=int)
    parser.add_argument("command", nargs="+")
    args = parser.parse_args()
    print(command(args.port, " ".join(args.command)))
