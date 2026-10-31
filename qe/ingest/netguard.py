"""SSRF-safe validation of user-supplied target endpoint URLs, with DNS pinning."""

from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_METADATA = (ipaddress.ip_network("169.254.0.0/16"), ipaddress.ip_network("fd00:ec2::/32"),
             ipaddress.ip_network("100.100.100.200/32"))
_EXTRA_DENY = tuple(ipaddress.ip_network(n) for n in (
    "100.64.0.0/10", "192.88.99.0/24", "198.18.0.0/15", "224.0.0.0/4", "240.0.0.0/4",
    "fec0::/10", "64:ff9b::/96", "2002::/16", "ff00::/8"))
MAX_ENDPOINT_LEN = 500
DEFAULT_PLATFORM_PORTS = frozenset({8000, 8001})

IP = ipaddress.IPv4Address | ipaddress.IPv6Address


class EndpointError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedEndpoint:
    """A validated endpoint pinned to one IP: connect to `ip`, send Host/SNI for `host`."""

    scheme: str
    host: str
    port: int
    ip: str
    path: str


def _unmap(ip: IP) -> IP:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _addresses(host: str) -> list[IP]:
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise EndpointError("endpoint host does not resolve") from None
    return [ipaddress.ip_address(str(i[4][0])) for i in infos]


def redact_url(url: str | None) -> str | None:
    """scheme://host[:port]/path only: drops userinfo, query and fragment."""
    if not url:
        return url
    p = urlsplit(url)
    host = p.hostname or ""
    host = f"[{host}]" if ":" in host else host
    port = f":{p.port}" if p.port else ""
    return f"{p.scheme}://{host}{port}{p.path}"


def _platform_ports() -> frozenset[int]:
    raw = os.environ.get("QE_UI_PORT", "")
    if raw.isdigit():
        return DEFAULT_PLATFORM_PORTS | {int(raw)}
    return DEFAULT_PLATFORM_PORTS


def _check_local(port: int, path: str) -> None:
    if os.environ.get("QE_ALLOW_LOCAL_ENDPOINTS") == "1":
        return
    if port in _platform_ports() or path.startswith("/api/") or path == "/api":
        raise EndpointError("localhost endpoints may not target the platform itself; set "
                            "QE_ALLOW_LOCAL_ENDPOINTS=1 to test a local app on that port")


def _check_public(ip: IP, allow_private: bool) -> None:
    ip = _unmap(ip)
    if any(ip in net for net in _METADATA if ip.version == net.version) or ip.is_link_local:
        raise EndpointError("link-local / cloud-metadata addresses are blocked")
    extra = any(ip in net for net in _EXTRA_DENY if ip.version == net.version)
    if ip.is_global and not extra:
        return
    if allow_private and ip.is_private and not ip.is_loopback and not extra \
            and not ip.is_unspecified and not ip.is_multicast and not ip.is_reserved:
        return
    raise EndpointError("endpoint resolves to a non-public address")


def resolve_endpoint(url: str, resolve: bool = True) -> ResolvedEndpoint:
    """Validate `url` and pin it to one validated IP (resolved exactly once)."""
    if not isinstance(url, str) or not url or len(url) > MAX_ENDPOINT_LEN:
        raise EndpointError("endpoint_url must be a non-empty string")
    if not url.isprintable() or " " in url or "\\" in url:
        raise EndpointError("endpoint_url contains forbidden characters")
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise EndpointError("credentials in the URL are not allowed")
    if parts.query or parts.fragment or url.endswith(("?", "#")) or "?" in url or "#" in url:
        raise EndpointError("query strings and fragments are not allowed in endpoint_url")
    if not host:
        raise EndpointError("endpoint_url needs a host")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        raise EndpointError("invalid port") from None
    local = host in LOCAL_HOSTS
    if parts.scheme not in ("http", "https"):
        raise EndpointError("only https (or http to localhost) is allowed")
    if parts.scheme == "http" and not local:
        raise EndpointError("plain http is only allowed for localhost; use https")
    path = parts.path or "/"
    if local:
        _check_local(port, path)
    chosen = ""
    if resolve or local:
        allow_private = os.environ.get("QE_ALLOW_PRIVATE_ENDPOINTS") == "1"
        addrs = _addresses(host)
        if not addrs:
            raise EndpointError("endpoint host does not resolve")
        for ip in addrs:
            if local:
                if not _unmap(ip).is_loopback:
                    raise EndpointError("localhost must resolve to loopback")
            else:
                _check_public(ip, allow_private)
        chosen = str(addrs[0])
    return ResolvedEndpoint(scheme=parts.scheme, host=host, port=port, ip=chosen, path=path)


def validate_endpoint_url(url: str, resolve: bool = True) -> str:
    """Return the url if safe (see resolve_endpoint). Metadata/CGNAT/non-global always blocked;
    RFC1918 needs QE_ALLOW_PRIVATE_ENDPOINTS=1; loopback is gated by _check_local."""
    resolve_endpoint(url, resolve)
    return url
