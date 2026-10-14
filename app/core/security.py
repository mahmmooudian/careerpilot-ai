"""Phase 7: same-machine boundary and browser response hardening.

This workspace deliberately has no account system.  Loopback checks are a
safety boundary for accidental LAN exposure, *not* a substitute for auth.
The ASGI middleware runs before Swagger, assets, and API routing.
"""
from __future__ import annotations

from urllib.parse import urlsplit
import os
import ipaddress
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

_LOOPBACK_PEERS = frozenset({'127.0.0.1', '::1', 'testclient'})
_LOOPBACK_HOSTS = frozenset({'127.0.0.1', '::1', 'localhost', 'testserver'})
_MUTATING = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})
MAX_DECLARED_REQUEST_BYTES = 10 * 1024 * 1024  # early rejection, not a streaming cap


def _safe_origin(value: str, *, scheme: str, host: str, port: int | None) -> bool:
    try:
        parsed = urlsplit(value)
        return (parsed.scheme == scheme and parsed.hostname == host
                and parsed.port == port and not parsed.username
                and not parsed.password and not parsed.path.strip('/')
                and not parsed.query and not parsed.fragment)
    except ValueError:
        return False


def is_local_peer(peer: str | None, host: str | None) -> bool:
    """Only local peers; explicit Docker bridge support for loopback-published Compose.

    Not authorization or a guarantee against unsafe Docker daemon settings.
    """
    if peer in _LOOPBACK_PEERS and host in _LOOPBACK_HOSTS:
        return True
    if os.getenv('CAREERPILOT_DOCKER_LOCAL') != '1':
        return False
    if host not in {'127.0.0.1', 'localhost', '::1'}:
        return False
    try:
        address = ipaddress.ip_address(peer or '')
        return address.is_private and not address.is_loopback and not address.is_link_local
    except ValueError:
        return False


class LocalSecurityMiddleware:
    """Reject non-loopback access, DNS rebinding and cross-site writes.

    This is an ASGI middleware so it does not buffer user resume documents.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        headers = Headers(scope=scope)
        host_header = headers.get('host', '')
        raw_client = scope.get('client')
        peer = raw_client[0] if raw_client else None
        scheme = scope.get('scheme', 'http')
        target = None
        try:
            target = urlsplit('//'+host_header)
            host = target.hostname
            port = target.port
        except ValueError:
            host, port = None, None
        if (not is_local_peer(peer, host)
                or not host_header or (target is not None and (target.username or target.password))):
            return await self._reject(scope, receive, send, 403, 'CareerPilot is restricted to loopback access')

        if scope.get('method') in _MUTATING:
            origin = headers.get('origin')
            if origin is not None and not _safe_origin(origin, scheme=scheme, host=host, port=port):
                return await self._reject(scope, receive, send, 403, 'Cross-origin writes are not allowed')
            site = (headers.get('sec-fetch-site') or '').lower()
            if site and site not in ('same-origin', 'none'):
                return await self._reject(scope, receive, send, 403, 'Cross-site writes are not allowed')
            content_length = headers.get('content-length')
            if content_length is not None:
                try:
                    declared = int(content_length)
                except ValueError:
                    return await self._reject(scope, receive, send, 400, 'Invalid content length')
                if declared < 0:
                    return await self._reject(scope, receive, send, 400, 'Invalid content length')
                if declared > MAX_DECLARED_REQUEST_BYTES:
                    return await self._reject(scope, receive, send, 413, 'Request body exceeds the configured limit')

        async def secured_send(message):
            if message['type'] == 'http.response.start':
                pairs = list(message.get('headers', []))
                names = {k.lower() for k, _ in pairs}
                standard = (
                    (b'x-content-type-options', b'nosniff'),
                    (b'x-frame-options', b'DENY'),
                    (b'referrer-policy', b'no-referrer'),
                    (b'permissions-policy', b'camera=(), microphone=(), geolocation=()'),
                )
                pairs.extend((k, v) for k, v in standard if k not in names)
                if scope.get('path', '').startswith('/api/') or scope.get('path') == '/health':
                    if b'cache-control' not in names:
                        pairs.append((b'cache-control', b'no-store'))
                message['headers'] = pairs
            await send(message)

        return await self.app(scope, receive, secured_send)

    @staticmethod
    async def _reject(scope, receive, send, code: int, detail: str):
        # Never reflect Origin, Host, token values, or request bodies.
        await JSONResponse({'detail':detail}, status_code=code,
                           headers={'Cache-Control':'no-store'})(scope, receive, send)
