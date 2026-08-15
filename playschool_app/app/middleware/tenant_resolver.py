from urllib.parse import urlparse

def extract_subdomain(host):
    """Extract the left-most subdomain from a host (without port).
    Returns None for localhost or bare domains.
    Examples:
      tenant.example.com -> tenant
      example.com -> None
      localhost -> None
    """
    if not host:
        return None
    host = host.split(':')[0]
    parts = host.split('.')
    if len(parts) < 3:
        return None
    return parts[0].lower()


def resolve_tenant(query_db_fn, host):
    """Resolve tenant metadata from the control DB using `query_db_fn`.
    Returns a dict row or None.
    """
    sub = extract_subdomain(host)
    if not sub:
        return None
    # Ignore common local/test subdomains
    if sub in ('www', 'api', 'app'):
        return None
    try:
        sch = query_db_fn("SELECT * FROM schools WHERE subdomain=%s", (sub,), one=True, use_control=True)
        return sch
    except Exception:
        return None
