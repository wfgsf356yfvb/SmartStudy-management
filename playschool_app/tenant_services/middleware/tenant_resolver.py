"""Trusted hostname validation and control-database tenant resolution."""

import re
from urllib.parse import urlsplit


class TenantResolutionError(ValueError):
    """Raised when a request cannot be mapped to an authorized tenant."""


_SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_RESERVED_SUBDOMAINS = {"www", "api", "app", "admin", "control"}


def validate_subdomain(subdomain):
    if not isinstance(subdomain, str):
        raise TenantResolutionError("Invalid tenant subdomain")
    value = subdomain.strip().lower()
    if not _SUBDOMAIN_RE.fullmatch(value) or value in _RESERVED_SUBDOMAINS:
        raise TenantResolutionError("Invalid tenant subdomain")
    return value


def _normalize_base_domain(base_domain):
    if not isinstance(base_domain, str):
        raise TenantResolutionError("Tenant base domain is not configured")
    value = base_domain.strip().lower().rstrip(".")
    if not value or ("." not in value and value != "localhost") or any(ch in value for ch in "/:@"):
        raise TenantResolutionError("Tenant base domain is invalid")
    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise TenantResolutionError("Tenant base domain is invalid") from exc
    labels = value.split(".")
    if any(not label or len(label) > 63 for label in labels):
        raise TenantResolutionError("Tenant base domain is invalid")
    return value


def normalize_host(host, allowed_ports=(80, 443, 5000)):
    """Return a normalized DNS hostname, rejecting ports and malformed hosts."""
    if not isinstance(host, str) or not host or any(ch in host for ch in "\\/@"):
        raise TenantResolutionError("Invalid request host")
    if host != host.strip() or host.endswith("."):
        raise TenantResolutionError("Invalid request host")
    parsed = urlsplit(f"//{host}")
    if parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise TenantResolutionError("Invalid request host")
    try:
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise TenantResolutionError("Invalid request host") from exc
    if not hostname or (port is not None and port not in allowed_ports):
        raise TenantResolutionError("Unexpected host port")
    try:
        hostname = hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise TenantResolutionError("Invalid request host") from exc
    if len(hostname) > 253 or any(not label for label in hostname.split(".")):
        raise TenantResolutionError("Invalid request host")
    return hostname


def extract_subdomain(host, base_domain, allowed_ports=(80, 443, 5000)):
    """Validate a hostname and return its single tenant label or ``None``."""
    base = _normalize_base_domain(base_domain)
    hostname = normalize_host(host, allowed_ports=allowed_ports)
    if hostname == base:
        return None
    suffix = f".{base}"
    if not hostname.endswith(suffix):
        raise TenantResolutionError("Host is outside the canonical base domain")
    prefix = hostname[: -len(suffix)]
    if "." in prefix or not prefix:
        raise TenantResolutionError("Nested or missing tenant subdomain")
    return validate_subdomain(prefix)


def resolve_tenant(query_db_fn, host, base_domain, allowed_ports=(80, 443, 5000)):
    """Resolve a tenant only through the control DB mapping.

    A bare canonical base domain is a control-plane request and returns None.
    Any tenant-looking, unknown, malformed, or infrastructure-failed host is
    rejected instead of falling through to the control database.
    """
    subdomain = extract_subdomain(host, base_domain, allowed_ports=allowed_ports)
    if subdomain is None:
        return None
    try:
        school = query_db_fn(
            "SELECT * FROM schools WHERE subdomain=%s",
            (subdomain,),
            one=True,
            use_control=True,
        )
    except Exception as exc:
        raise TenantResolutionError("Tenant lookup failed") from exc
    if not school:
        raise TenantResolutionError("Unknown tenant")
    if str(school.get("subdomain", "")).lower() != subdomain:
        raise TenantResolutionError("Tenant mapping mismatch")
    if school.get("subscription_status") in {"provisioning", "disabled", "deleted"}:
        raise TenantResolutionError("Tenant is not active")
    return school
