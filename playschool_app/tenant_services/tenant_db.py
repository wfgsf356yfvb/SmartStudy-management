"""Tenant database connections backed by server-side credential records."""

from collections import OrderedDict
import hashlib
import json
import re

from mysql.connector import pooling
from config import Config
from tenant_services.secrets_manager import get_tenant_db_credentials
from tenant_services.middleware.tenant_resolver import validate_subdomain


_MAX_POOLS = 12
_pools = OrderedDict()
_DATABASE_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_HOST_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}$")


def _tenant_reference(tenant):
    if not isinstance(tenant, dict):
        raise ValueError("Tenant connection requires a resolved tenant record")
    subdomain = validate_subdomain(tenant.get("subdomain"))
    return subdomain


def _load_credentials(tenant):
    subdomain = _tenant_reference(tenant)
    credentials = get_tenant_db_credentials(subdomain)
    if not isinstance(credentials, dict):
        raise RuntimeError("Tenant database credentials are unavailable")

    database = credentials.get("database")
    username = credentials.get("username")
    password = credentials.get("password")
    host = credentials.get("host", Config.MYSQL_HOST)
    port = credentials.get("port", Config.MYSQL_PORT)
    if not isinstance(database, str) or not _DATABASE_RE.fullmatch(database):
        raise RuntimeError("Tenant database mapping is invalid")
    if not isinstance(username, str) or not username or username.lower() == "root":
        raise RuntimeError("Tenant database user is invalid")
    if not isinstance(password, str) or not password:
        raise RuntimeError("Tenant database password is unavailable")
    if not isinstance(host, str) or not _HOST_RE.fullmatch(host) or host.startswith("."):
        raise RuntimeError("Tenant database host is invalid")
    try:
        port = int(port)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Tenant database port is invalid") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("Tenant database port is invalid")
    return {
        "host": host,
        "port": port,
        "database": database,
        "username": username,
        "password": password,
    }


def _pool_key(subdomain, credentials):
    fingerprint = hashlib.sha256(
        json.dumps(credentials, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return subdomain, fingerprint


def _close_pool(pool):
    remover = getattr(pool, "_remove_connections", None)
    if callable(remover):
        try:
            remover()
        except Exception:
            pass


def _create_pool_for(subdomain, credentials, fingerprint):
    pool_name = "playschool_pool_" + hashlib.sha256(
        f"{subdomain}:{fingerprint}".encode()
    ).hexdigest()[:24]
    cfg = {
        "host": credentials["host"],
        "user": credentials["username"],
        "password": credentials["password"],
        "database": credentials["database"],
        "port": credentials["port"],
        "charset": "utf8mb4",
        "collation": "utf8mb4_unicode_ci",
        "autocommit": False,
    }
    return pooling.MySQLConnectionPool(
        pool_name=pool_name,
        pool_size=3,
        pool_reset_session=True,
        **cfg,
    )


def get_pool(tenant):
    subdomain = _tenant_reference(tenant)
    credentials = _load_credentials(tenant)
    key = _pool_key(subdomain, credentials)
    existing = _pools.get(subdomain)
    if existing and existing[0] == key:
        _pools.move_to_end(subdomain)
        return existing[1]
    if existing:
        _close_pool(existing[1])
        del _pools[subdomain]
    pool = _create_pool_for(subdomain, credentials, key[1])
    _pools[subdomain] = (key, pool)
    if len(_pools) > _MAX_POOLS:
        _, evicted = _pools.popitem(last=False)
        _close_pool(evicted[1])
    return pool


def get_connection_for_tenant(tenant):
    """Return a connection for an already-resolved tenant record only."""
    return get_pool(tenant).get_connection()
