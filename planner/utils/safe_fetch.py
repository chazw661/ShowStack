"""Fetch a user-supplied URL without letting it reach the private network.

Used by the Mic Tracker's drag-an-image-from-another-site upload, which hands
the server an arbitrary URL. The old fetch checked the hostname's addresses and
then called ``requests.get(url)``. That left three ways in:

1. **DNS rebinding.** ``requests`` resolved the name a second time. A host whose
   DNS answers a public address to the check and ``169.254.169.254`` to the
   connect sailed through.
2. **Redirects.** ``requests`` follows them by default, and only the first hop
   was checked. A public URL answering ``302 Location: http://10.0.0.5/`` was
   fetched.
3. **No overall deadline.** A server trickling one byte per 9 seconds never
   tripped the 10s read timeout.

So: resolve once, refuse unless *every* address is public, and connect to the
address that was checked -- not to the name. TLS still verifies the
certificate against the real hostname (SNI + ``assert_hostname``). Redirects are
followed by hand, a few hops at most, and each hop goes through the same check.
A single monotonic deadline covers the whole thing, and the body is cut off at
``max_bytes``.
"""

import ipaddress
import socket
import time
import urllib.parse

import certifi
import urllib3

ALLOWED_PORTS = {'http': 80, 'https': 443}
MAX_REDIRECTS = 3
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class UnsafeFetchError(Exception):
    """The URL was refused or could not be fetched. ``str()`` is user-safe."""


def _public_ip(raw):
    """The address as an ip_address if it is publicly routable, else None."""
    try:
        ip = ipaddress.ip_address(raw.split('%', 1)[0])
    except ValueError:
        return None
    # ::ffff:10.0.0.1 is 10.0.0.1. Python < 3.13 does not apply the IPv4
    # rules to mapped addresses, and prod runs 3.11.
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if not ip.is_global or ip.is_multicast:
        return None
    return ip


def resolve_public(hostname, port):
    """Resolve ``hostname`` once; return one address, or raise.

    Every returned address must be public. Picking the first public one and
    ignoring a private sibling would let a name with both records steer
    whichever path a later resolver happens to take.
    """
    try:
        infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        raise UnsafeFetchError('Cannot resolve host')
    if not infos:
        raise UnsafeFetchError('Cannot resolve host')
    addresses = []
    for info in infos:
        ip = _public_ip(info[4][0])
        if ip is None:
            raise UnsafeFetchError('Refused: internal host')
        addresses.append(ip)
    return str(addresses[0])


def _open(scheme, ip, port, hostname, path, timeout):
    """One request to a pinned address. Split out so tests can see the pin."""
    headers = {
        'Host': hostname if port == ALLOWED_PORTS[scheme] else f'{hostname}:{port}',
        'User-Agent': 'ShowStack-PhotoFetch/1.0',
        'Accept': 'image/*',
        # Ask for the bytes as stored. A decoded gzip stream can expand far
        # past max_bytes inside one read before the cap is checked.
        'Accept-Encoding': 'identity',
    }
    if scheme == 'https':
        pool = urllib3.HTTPSConnectionPool(
            ip, port,
            cert_reqs='CERT_REQUIRED', ca_certs=certifi.where(),
            server_hostname=hostname, assert_hostname=hostname,
            timeout=timeout, retries=False,
        )
    else:
        pool = urllib3.HTTPConnectionPool(ip, port, timeout=timeout, retries=False)
    return pool.urlopen(
        'GET', path, headers=headers, redirect=False, retries=False,
        preload_content=False, decode_content=False,
    )


def _split(url):
    parsed = urllib.parse.urlsplit(url)
    scheme = (parsed.scheme or '').lower()
    if scheme not in ALLOWED_PORTS or not parsed.hostname:
        raise UnsafeFetchError('Only http(s) URLs accepted')
    if parsed.username or parsed.password:
        raise UnsafeFetchError('URLs with credentials are not accepted')
    try:
        port = parsed.port or ALLOWED_PORTS[scheme]
    except ValueError:
        raise UnsafeFetchError('Invalid port')
    # Only the standard port for the scheme: an image link never needs
    # another, and allowing any turns this into a port scanner.
    if port != ALLOWED_PORTS[scheme]:
        raise UnsafeFetchError('Only standard ports are accepted')
    path = parsed.path or '/'
    if parsed.query:
        path += '?' + parsed.query
    return scheme, parsed.hostname, port, path


def fetch_public(url, max_bytes, total_timeout=15.0, read_timeout=10.0):
    """GET ``url`` from the public internet; return ``(body_bytes, headers)``.

    Raises UnsafeFetchError for anything refused, failed, too big or too slow.
    """
    deadline = time.monotonic() + total_timeout

    def remaining():
        left = deadline - time.monotonic()
        if left <= 0:
            raise UnsafeFetchError('Fetch timed out')
        return left

    for _hop in range(MAX_REDIRECTS + 1):
        scheme, hostname, port, path = _split(url)
        ip = resolve_public(hostname, port)
        left = remaining()
        timeout = urllib3.Timeout(connect=min(5.0, left), read=min(read_timeout, left))
        try:
            resp = _open(scheme, ip, port, hostname, path, timeout)
        except urllib3.exceptions.HTTPError as e:
            raise UnsafeFetchError(f'Fetch failed: {type(e).__name__}')

        try:
            if resp.status in REDIRECT_STATUSES:
                location = resp.headers.get('Location')
                if not location:
                    raise UnsafeFetchError('Redirect without a Location')
                url = urllib.parse.urljoin(url, location)
                continue
            if resp.status != 200:
                raise UnsafeFetchError(f'Fetch failed: HTTP {resp.status}')

            declared = resp.headers.get('Content-Length')
            if declared and declared.isdigit() and int(declared) > max_bytes:
                raise UnsafeFetchError(f'Image exceeds {max_bytes // (1024 * 1024)} MB limit')

            buf = bytearray()
            try:
                for chunk in resp.stream(64 * 1024):
                    buf.extend(chunk)
                    if len(buf) > max_bytes:
                        raise UnsafeFetchError(
                            f'Image exceeds {max_bytes // (1024 * 1024)} MB limit')
                    remaining()
            except urllib3.exceptions.HTTPError as e:
                raise UnsafeFetchError(f'Fetch failed: {type(e).__name__}')
            return bytes(buf), resp.headers
        finally:
            resp.release_conn()
            resp.close()

    raise UnsafeFetchError('Too many redirects')
