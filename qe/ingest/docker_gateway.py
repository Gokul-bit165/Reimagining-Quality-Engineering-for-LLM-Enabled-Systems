"""Source of the sidecar that runs inside the gateway container (stdlib only, no installs).

The gateway is the only container attached to both the isolated `--internal` network and a normal
bridge. It does two things:
  * ingress: a TCP forwarder on :8000 -> the app, so the host can reach the app through a
    loopback-published port (Docker does not publish ports of containers that sit only on an
    internal network);
  * egress (opt-in): an HTTP CONNECT forward proxy on :3128 that tunnels to port 443 of hosts on
    an explicit allowlist and refuses everything else. Every decision is logged as one JSON line.
It never sees provider keys: they travel inside the TLS tunnel between the app and the provider.
"""

from __future__ import annotations

import re

GATEWAY_INGRESS_PORT = 8000
GATEWAY_PROXY_PORT = 3128
_HOST = re.compile(r"^(\*\.)?([a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")

GATEWAY_SOURCE = r'''
import asyncio, ipaddress, json, os, socket, time

UP = (os.environ["QE_UPSTREAM_HOST"], int(os.environ["QE_UPSTREAM_PORT"]))
ALLOW = [h for h in os.environ.get("QE_ALLOW", "").lower().split(",") if h]
IDLE_S = 120
LIMIT = asyncio.Semaphore(64)


def log(**kw):
    print(json.dumps({"ts": round(time.time(), 3), **kw}), flush=True)


def allowed(host):
    host = host.lower().rstrip(".")
    for a in ALLOW:
        if a.startswith("*."):
            if host.endswith(a[1:]) and len(host) > len(a) - 1:
                return True
        elif host == a:
            return True
    return False


async def pump(r, w):
    try:
        while True:
            data = await asyncio.wait_for(r.read(65536), IDLE_S)
            if not data:
                break
            w.write(data)
            await w.drain()
    except Exception:
        pass
    finally:
        try:
            w.close()
        except Exception:
            pass


async def ingress(cr, cw):
    try:
        ur, uw = await asyncio.open_connection(*UP)
    except OSError:
        cw.close()
        return
    await asyncio.gather(pump(cr, uw), pump(ur, cw))


async def deny(cw, code, host, port, reason):
    log(event="deny", host=host[:200], port=port, reason=reason)
    try:
        head = "HTTP/1.1 %d X\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        cw.write((head % code).encode())
        await cw.drain()
    except Exception:
        pass
    cw.close()


async def proxy(cr, cw):
    async with LIMIT:
        try:
            line = (await asyncio.wait_for(cr.readline(), 10)).decode("latin-1").split()
            for _ in range(100):
                h = await asyncio.wait_for(cr.readline(), 10)
                if h in (b"\r\n", b"\n", b""):
                    break
        except Exception:
            cw.close()
            return
        if len(line) < 2 or line[0] != "CONNECT":
            return await deny(cw, 405, " ".join(line[1:2]), 0, "only CONNECT is allowed")
        host, _, port = line[1].rpartition(":")
        host = host.strip("[]")
        if port != "443":
            return await deny(cw, 403, host, port, "only port 443 is allowed")
        if not allowed(host):
            return await deny(cw, 403, host, 443, "host not in allowlist")
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                host, 443, type=socket.SOCK_STREAM)
            ips = [ipaddress.ip_address(i[4][0]) for i in infos]
            ips = [i.ipv4_mapped if getattr(i, "ipv4_mapped", None) else i for i in ips]
        except Exception:
            return await deny(cw, 502, host, 443, "does not resolve")
        if not ips or not all(i.is_global for i in ips):
            return await deny(cw, 403, host, 443, "resolves to a non-public address")
        try:
            ur, uw = await asyncio.wait_for(asyncio.open_connection(str(ips[0]), 443), 15)
        except Exception:
            return await deny(cw, 502, host, 443, "upstream connect failed")
        log(event="allow", host=host, port=443)
        cw.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await cw.drain()
        await asyncio.gather(pump(cr, uw), pump(ur, cw))


async def main():
    a = await asyncio.start_server(ingress, "0.0.0.0", 8000)
    b = await asyncio.start_server(proxy, "0.0.0.0", 3128)
    log(event="ready", allow=ALLOW)
    async with a, b:
        await asyncio.gather(a.serve_forever(), b.serve_forever())


asyncio.run(main())
'''


def validate_egress_hosts(hosts: list[str]) -> list[str]:
    """Normalise and validate an allowlist: exact DNS names or `*.suffix`, never IPs or ports."""
    out: list[str] = []
    for raw in hosts:
        h = raw.strip().lower()
        if not _HOST.match(h) or len(h) > 253:
            raise ValueError(f"invalid egress host {raw[:60]!r}: use a DNS name such as "
                             "api.openai.com (or *.example.com); no schemes, ports, paths or IPs")
        if h not in out:
            out.append(h)
    return out
