#!/usr/bin/env python3
"""Validate DNS cutover prerequisites without changing external state."""

from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path


HOSTS = (
    "app.svoi-kanal.ru",
    "admin.svoi-kanal.ru",
    "platform.svoi-kanal.ru",
    "proxy.svoi-kanal.ru",
)
REQUIRED = {
    "app.svoi-kanal.ru": "reverse_proxy bot:8000",
    "admin.svoi-kanal.ru": "reverse_proxy admin:3000",
    "platform.svoi-kanal.ru": "reverse_proxy platform-admin:3000",
    "proxy.svoi-kanal.ru": "reverse_proxy xray:10000",
}


def resolve(host: str) -> set[str]:
    try:
        return {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except socket.gaierror:
        return set()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-ip")
    parser.add_argument("--require-dns", action="store_true")
    args = parser.parse_args()
    caddy = Path("Caddyfile").read_text(encoding="utf-8")
    config_ok = all(host in caddy and target in caddy for host, target in REQUIRED.items())
    dns = {host: sorted(resolve(host)) for host in HOSTS}
    dns_ok = all(dns.values())
    if args.expected_ip:
        dns_ok = dns_ok and all(args.expected_ip in addresses for addresses in dns.values())
    print(json.dumps({"config_ok": config_ok, "dns_ok": dns_ok, "dns": dns}, ensure_ascii=False))
    return 0 if config_ok and (dns_ok or not args.require_dns) else 1


if __name__ == "__main__":
    raise SystemExit(main())
