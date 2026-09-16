"""Automatic HTTPS for the A2 Listen companion (Issue #74).

iOS Safari only plays WebRTC audio from a secure origin, so phones need the
companion on HTTPS with a certificate they trust. Instead of asking users to
install mkcert, the companion keeps its own tiny certificate authority:

* A per-Mac local CA, created once. It is **name-constrained** to private LAN
  addresses, `.local` names and `localhost`, so even if its key leaked it could
  not be used to impersonate real websites to a phone that trusts it.
* A server certificate for every current LAN IPv4 + `<host>.local` +
  `localhost`, reissued automatically when the Mac's addresses change.
* A `.mobileconfig` profile of the CA certificate that a phone can download
  and trust once (Settings → General → About → Certificate Trust Settings).
"""

import datetime
import ipaddress
import json
import os
import plistlib
import re
import socket
import ssl
import subprocess
import uuid

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

APP_NAME = "ShowStack Listen"
SERVER_DAYS = 397                 # stay under Apple's TLS server-cert lifetime limits
RENEW_BEFORE_DAYS = 30

# Everything the CA is allowed to vouch for.
PERMITTED_NETWORKS = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
                      "169.254.0.0/16", "100.64.0.0/10", "127.0.0.0/8")
PERMITTED_DNS = ("local", "localhost")


def support_dir():
    path = os.path.expanduser("~/Library/Application Support/%s" % APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def _paths(directory):
    return {
        "ca_key": os.path.join(directory, "ca.key.pem"),
        "ca_cert": os.path.join(directory, "ca.pem"),
        "key": os.path.join(directory, "server.key.pem"),
        "cert": os.path.join(directory, "server.pem"),
        "meta": os.path.join(directory, "server.json"),
    }


def _write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def lan_ipv4s():
    """Every private/link-local IPv4 on this Mac, sorted (no loopback)."""
    found = set()
    try:
        out = subprocess.run(["/sbin/ifconfig"], capture_output=True, text=True, timeout=5).stdout
        found.update(re.findall(r"\binet (\d+\.\d+\.\d+\.\d+)", out))
    except Exception:
        pass
    try:
        found.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except Exception:
        pass
    permitted = [ipaddress.ip_network(n) for n in PERMITTED_NETWORKS if not n.startswith("127.")]
    ips = []
    for ip in found:
        addr = ipaddress.ip_address(ip)
        if any(addr in net for net in permitted):
            ips.append(ip)
    return sorted(ips, key=lambda s: tuple(int(p) for p in s.split(".")))


def local_hostname():
    try:
        name = subprocess.run(["/usr/sbin/scutil", "--get", "LocalHostName"],
                              capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        name = ""
    return (name or socket.gethostname().split(".")[0]) + ".local"


def ensure_ca(directory=None):
    """Create the local CA once. Returns (key, cert)."""
    p = _paths(directory or support_dir())
    if os.path.exists(p["ca_key"]) and os.path.exists(p["ca_cert"]):
        with open(p["ca_key"], "rb") as fh:
            key = serialization.load_pem_private_key(fh.read(), password=None)
        with open(p["ca_cert"], "rb") as fh:
            cert = x509.load_pem_x509_certificate(fh.read())
        return key, cert

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME,
                           "ShowStack Listen Local CA (%s)" % local_hostname()),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ShowStack Listen"),
    ])
    constraints = x509.NameConstraints(
        permitted_subtrees=[x509.IPAddress(ipaddress.ip_network(n)) for n in PERMITTED_NETWORKS]
        + [x509.DNSName(d) for d in PERMITTED_DNS],
        excluded_subtrees=None,
    )
    now = _now()
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=False, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True,
            crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(constraints, critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    _write_private(p["ca_key"], key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))
    with open(p["ca_cert"], "wb") as fh:
        fh.write(cert.public_bytes(serialization.Encoding.PEM))
    return key, cert


def ensure_server_cert(directory=None):
    """(Re)issue the server cert if missing, expiring, or the LAN IPs changed.

    Returns (cert_path, key_path, sans) where sans = {"ips": [...], "dns": [...]}.
    """
    directory = directory or support_dir()
    p = _paths(directory)
    ca_key, ca_cert = ensure_ca(directory)
    sans = {"ips": lan_ipv4s() + ["127.0.0.1"], "dns": [local_hostname(), "localhost"]}

    try:
        with open(p["meta"]) as fh:
            meta = json.load(fh)
        with open(p["cert"], "rb") as fh:
            current = x509.load_pem_x509_certificate(fh.read())
        fresh = (
            meta.get("sans") == sans
            and meta.get("ca_serial") == ca_cert.serial_number
            and current.not_valid_after_utc - _now() > datetime.timedelta(days=RENEW_BEFORE_DAYS)
            and os.path.exists(p["key"])
        )
    except (OSError, ValueError):
        fresh = False
    if fresh:
        return p["cert"], p["key"], sans

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = _now()
    alt_names = [x509.DNSName(d) for d in sans["dns"]] + \
        [x509.IPAddress(ipaddress.ip_address(ip)) for ip in sans["ips"]]
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, sans["dns"][0])]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=SERVER_DAYS))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=True,
            data_encipherment=False, key_agreement=False, key_cert_sign=False,
            crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
                       critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    _write_private(p["key"], key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))
    with open(p["cert"], "wb") as fh:
        # Full chain so clients that only trust the CA can build the path.
        fh.write(cert.public_bytes(serialization.Encoding.PEM))
        fh.write(ca_cert.public_bytes(serialization.Encoding.PEM))
    with open(p["meta"], "w") as fh:
        json.dump({"sans": sans, "ca_serial": ca_cert.serial_number}, fh)
    return p["cert"], p["key"], sans


def server_ssl_context(directory=None):
    cert, key, sans = ensure_server_cert(directory)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    return ctx, sans


def ca_mobileconfig(directory=None):
    """(bytes, content_type, filename) — an iOS profile that installs the CA."""
    _key, ca_cert = ensure_ca(directory)
    der = ca_cert.public_bytes(serialization.Encoding.DER)
    fingerprint = ca_cert.fingerprint(hashes.SHA256()).hex()
    ns = uuid.UUID("5b0c1c4e-7f1f-4b7e-9d0e-5d7a3a1a7474")
    profile = {
        "PayloadType": "Configuration",
        "PayloadVersion": 1,
        "PayloadIdentifier": "io.showstack.listen.ca.%s" % fingerprint[:16],
        "PayloadUUID": str(uuid.uuid5(ns, "profile:" + fingerprint)).upper(),
        "PayloadDisplayName": "ShowStack Listen (%s)" % local_hostname(),
        "PayloadDescription": "Lets this device play A2 Listen audio from the ShowStack "
                              "Listen app on %s. Only valid for local network addresses."
                              % local_hostname(),
        "PayloadOrganization": "ShowStack",
        "PayloadContent": [{
            "PayloadType": "com.apple.security.root",
            "PayloadVersion": 1,
            "PayloadIdentifier": "io.showstack.listen.ca.cert.%s" % fingerprint[:16],
            "PayloadUUID": str(uuid.uuid5(ns, "cert:" + fingerprint)).upper(),
            "PayloadDisplayName": ca_cert.subject.get_attributes_for_oid(
                NameOID.COMMON_NAME)[0].value,
            "PayloadContent": der,
        }],
    }
    return plistlib.dumps(profile), "application/x-apple-aspen-config", \
        "ShowStack-Listen-%s.mobileconfig" % local_hostname().split(".")[0]
