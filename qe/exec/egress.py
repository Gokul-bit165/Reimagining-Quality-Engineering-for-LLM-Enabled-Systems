"""In-process network egress guard.

Scope (honest limits): patches Python-level networking in this process only. It does
NOT contain subprocesses, native extensions that open their own sockets, or code that
captured `_socket` functions before the guard started. Container/network-namespace
egress control is a later milestone (M4).

Covered: socket connect/connect_ex/sendto, getaddrinfo/gethostbyname[_ex]/getnameinfo,
and asyncio's loop.create_connection / create_datagram_endpoint / sock_connect (needed
because the Windows Proactor loop connects without calling socket.connect).

Patches are installed once and reference-counted; overlapping or non-LIFO guards are
safe. A host must be allowed by EVERY active guard (most restrictive wins).
"""

from __future__ import annotations

import asyncio
import socket
import threading
from collections.abc import Callable
from types import TracebackType
from typing import Any, Self


class EgressBlockedError(ConnectionError):
    pass


_LOCK = threading.RLock()
_BYPASS = threading.local()  # socketpair() internals connect over loopback (Windows)
_ACTIVE: list[EgressGuard] = []
_ORIGINALS: dict[tuple[Any, str], Any] = {}

_SOCKET_METHODS = ("connect", "connect_ex", "sendto")
_HOST_FUNCS = ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "getnameinfo")
_LOOP_METHODS = ("create_connection", "sock_connect", "create_datagram_endpoint")

_LOOP_CLASSES: list[type] = [asyncio.BaseEventLoop]
for _name in ("ProactorEventLoop", "SelectorEventLoop"):
    _cls = getattr(asyncio, _name, None)
    if _cls is not None:
        _LOOP_CLASSES.append(_cls)


def _host_of(address: Any) -> str:
    if isinstance(address, tuple) and address:
        return str(address[0])
    return str(address)


def _port(address: Any) -> object:
    return address[1] if isinstance(address, tuple) and len(address) > 1 else None


def _check(host: str, port: object = None) -> None:
    if getattr(_BYPASS, "depth", 0) > 0:
        return
    with _LOCK:
        blocked = [g for g in _ACTIVE if host not in g._allow]
        if not blocked:
            return
        label = f"{host}:{port}" if port is not None else host
        for g in blocked:
            g.attempts.append(label)
    raise EgressBlockedError(f"egress to {host!r} blocked by sandbox allowlist")


def _is_ip_socket(sock: Any) -> bool:
    return getattr(sock, "family", None) in (socket.AF_INET, socket.AF_INET6)


def _wrap_sock_method(orig: Callable[..., Any]) -> Callable[..., Any]:
    def wrapper(sock: socket.socket, *args: Any, **kwargs: Any) -> Any:
        address = args[-1] if args else kwargs.get("address")
        if _is_ip_socket(sock) and address is not None:
            _check(_host_of(address), _port(address))
        return orig(sock, *args, **kwargs)

    return wrapper


def _wrap_host_func(name: str, orig: Callable[..., Any]) -> Callable[..., Any]:
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if name == "getnameinfo":
            _check(_host_of(args[0]))
        else:
            host = args[0] if args else kwargs.get("host", kwargs.get("hostname"))
            if host is not None:
                _check(str(host))
        return orig(*args, **kwargs)

    return wrapper


def _wrap_socketpair(orig: Callable[..., Any]) -> Callable[..., Any]:
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        _BYPASS.depth = getattr(_BYPASS, "depth", 0) + 1
        try:
            return orig(*args, **kwargs)
        finally:
            _BYPASS.depth -= 1

    return wrapper


def _wrap_create_connection(orig: Callable[..., Any]) -> Callable[..., Any]:
    async def wrapper(self: Any, protocol_factory: Any, host: Any = None, port: Any = None,
                      **kwargs: Any) -> Any:
        if host is not None:
            _check(str(host), port)
        return await orig(self, protocol_factory, host, port, **kwargs)

    return wrapper


def _wrap_sock_connect(orig: Callable[..., Any]) -> Callable[..., Any]:
    async def wrapper(self: Any, sock: Any, address: Any) -> Any:
        if _is_ip_socket(sock):
            _check(_host_of(address), _port(address))
        return await orig(self, sock, address)

    return wrapper


def _wrap_datagram(orig: Callable[..., Any]) -> Callable[..., Any]:
    async def wrapper(self: Any, protocol_factory: Any, local_addr: Any = None,
                      remote_addr: Any = None, **kwargs: Any) -> Any:
        if remote_addr is not None:
            _check(_host_of(remote_addr), _port(remote_addr))
        return await orig(self, protocol_factory, local_addr, remote_addr, **kwargs)

    return wrapper


_LOOP_WRAPPERS: dict[str, Callable[[Callable[..., Any]], Callable[..., Any]]] = {
    "create_connection": _wrap_create_connection,
    "sock_connect": _wrap_sock_connect,
    "create_datagram_endpoint": _wrap_datagram,
}


def _install() -> None:
    for name in _SOCKET_METHODS:
        orig = getattr(socket.socket, name)
        _ORIGINALS[(socket.socket, name)] = orig
        setattr(socket.socket, name, _wrap_sock_method(orig))  # noqa: B010
    for name in _HOST_FUNCS:
        orig = getattr(socket, name)
        _ORIGINALS[(socket, name)] = orig
        setattr(socket, name, _wrap_host_func(name, orig))
    pair = socket.socketpair
    _ORIGINALS[(socket, "socketpair")] = pair
    socket.socketpair = _wrap_socketpair(pair)
    for cls in _LOOP_CLASSES:
        for base in cls.__mro__[:-1]:  # the defining class may be a base (Proactor)
            for name in _LOOP_METHODS:
                if name in vars(base) and (base, name) not in _ORIGINALS:
                    orig = vars(base)[name]
                    _ORIGINALS[(base, name)] = orig
                    setattr(base, name, _LOOP_WRAPPERS[name](orig))


def _uninstall() -> None:
    for (owner, name), orig in _ORIGINALS.items():
        setattr(owner, name, orig)
    _ORIGINALS.clear()


class EgressGuard:
    def __init__(self, allowlist: tuple[str, ...] = ()) -> None:
        self._allow = frozenset(allowlist)
        self.attempts: list[str] = []

    def __enter__(self) -> Self:
        with _LOCK:
            if not _ACTIVE:
                _install()
            _ACTIVE.append(self)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        with _LOCK:
            _ACTIVE.remove(self)
            if not _ACTIVE:
                _uninstall()
