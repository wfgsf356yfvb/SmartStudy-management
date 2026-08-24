"""Mocked isolation tests for Phase 2 tenant boundaries."""

import importlib
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from tenant_services.middleware.tenant_resolver import (  # noqa: E402
    TenantResolutionError,
    extract_subdomain,
    resolve_tenant,
)
from tenant_services.job_context import (  # noqa: E402
    TenantJobContextError,
    make_tenant_job_ref,
    resolve_tenant_job_ref,
    validate_tenant_job_ref,
)
from tenant_services import secrets_manager  # noqa: E402



class FakeConnection:
    def __init__(self, database):
        self.database = database


class FakePool:
    created = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False
        self.created.append(self)

    def get_connection(self):
        return FakeConnection(self.kwargs["database"])

    def _remove_connections(self):
        self.closed = True


def load_tenant_db_with_fake_mysql():
    try:
        import mysql.connector  # noqa: F401
        module = importlib.import_module("tenant_services.tenant_db")
        module.pooling.MySQLConnectionPool = FakePool
        return module
    except ModuleNotFoundError:
        connector = types.ModuleType("mysql.connector")
        connector.pooling = types.SimpleNamespace(MySQLConnectionPool=FakePool)
        mysql = types.ModuleType("mysql")
        mysql.connector = connector
        sys.modules["mysql"] = mysql
        sys.modules["mysql.connector"] = connector
        return importlib.import_module("tenant_services.tenant_db")


tenant_db = load_tenant_db_with_fake_mysql()


class TenantResolverTests(unittest.TestCase):
    def setUp(self):
        self.records = {
            "alpha": {"id": 1, "subdomain": "alpha", "database": "ignored-client-field"},
            "beta": {"id": 2, "subdomain": "beta"},
        }

    def lookup(self, sql, args, **kwargs):
        self.assertTrue(kwargs["use_control"])
        return self.records.get(args[0])

    def test_valid_hosts_map_through_control_db(self):
        self.assertEqual(extract_subdomain("alpha.example.com:443", "example.com"), "alpha")
        self.assertEqual(resolve_tenant(self.lookup, "alpha.example.com", "example.com")["id"], 1)

    def test_base_unknown_and_malformed_hosts_fail_closed(self):
        self.assertIsNone(resolve_tenant(self.lookup, "example.com", "example.com"))
        with self.assertRaises(TenantResolutionError):
            resolve_tenant(self.lookup, "", "example.com")
        with self.assertRaises(TenantResolutionError):
            resolve_tenant(self.lookup, "unknown.example.com", "example.com")
        with self.assertRaises(TenantResolutionError):
            resolve_tenant(self.lookup, "alpha.attacker.example.com", "example.com")
        with self.assertRaises(TenantResolutionError):
            resolve_tenant(self.lookup, "alpha.example.com:3306", "example.com")
        with self.assertRaises(TenantResolutionError):
            resolve_tenant(self.lookup, "alpha.example.com/other", "example.com")

    def test_control_lookup_failure_does_not_fall_back(self):
        def failed_lookup(*args, **kwargs):
            raise RuntimeError("control DB unavailable")

        with self.assertRaises(TenantResolutionError):
            resolve_tenant(failed_lookup, "alpha.example.com", "example.com")

    def test_host_resolution_has_no_browser_tenant_override(self):
        resolved = resolve_tenant(self.lookup, "alpha.example.com", "example.com")
        self.assertEqual(resolved["subdomain"], "alpha")
        self.assertNotIn("tenant_id", resolved)


class TenantPoolIsolationTests(unittest.TestCase):
    def setUp(self):
        FakePool.created.clear()
        tenant_db._pools.clear()
        self.credentials = {
            "alpha": {
                "host": "127.0.0.1",
                "port": 3306,
                "database": "playschool_tenant_alpha",
                "username": "playschool_alpha",
                "password": "phase2-test-alpha",
            },
            "beta": {
                "host": "127.0.0.1",
                "port": 3306,
                "database": "playschool_tenant_beta",
                "username": "playschool_beta",
                "password": "phase2-test-beta",
            },
        }
        tenant_db.get_tenant_db_credentials = lambda subdomain: self.credentials[subdomain]

    def test_each_tenant_gets_only_its_mapped_database(self):
        alpha = tenant_db.get_connection_for_tenant({"subdomain": "alpha"})
        beta = tenant_db.get_connection_for_tenant({"subdomain": "beta"})
        self.assertEqual(alpha.database, "playschool_tenant_alpha")
        self.assertEqual(beta.database, "playschool_tenant_beta")
        self.assertNotEqual(alpha.database, beta.database)
        self.assertEqual(FakePool.created[0].kwargs["user"], "playschool_alpha")
        self.assertEqual(FakePool.created[1].kwargs["user"], "playschool_beta")

    def test_pool_cache_is_tenant_keyed_and_replaces_changed_credentials(self):
        first = tenant_db.get_pool({"subdomain": "alpha"})
        tenant_db.get_pool({"subdomain": "beta"})
        self.credentials["alpha"] = dict(self.credentials["alpha"], password="rotated-phase2-test-alpha")
        second = tenant_db.get_pool({"subdomain": "alpha"})
        self.assertIsNot(first, second)
        self.assertTrue(first.closed)
        self.assertEqual(second.kwargs["database"], "playschool_tenant_alpha")

    def test_client_cannot_supply_database_or_root_credentials(self):
        with self.assertRaises(ValueError):
            tenant_db.get_pool("alpha")
        self.credentials["alpha"] = dict(self.credentials["alpha"], database="playschool_tenant_beta")
        self.assertEqual(
            tenant_db.get_pool({"subdomain": "alpha"}).get_connection().database,
            "playschool_tenant_beta",
        )
        self.credentials["alpha"] = dict(self.credentials["alpha"], username="root")
        with self.assertRaises(RuntimeError):
            tenant_db.get_pool({"subdomain": "alpha"})


class CredentialProviderTests(unittest.TestCase):
    def setUp(self):
        self.records = {
            "alpha": {"database": "playschool_tenant_alpha", "username": "playschool_alpha", "password": "alpha-test"},
            "beta": {"database": "playschool_tenant_beta", "username": "playschool_beta", "password": "beta-test"},
        }

    def test_environment_provider_keeps_tenant_credentials_separate(self):
        with patch.dict(
            os.environ,
            {
                "FLASK_ENV": "production",
                "TENANT_CREDENTIAL_PROVIDER": "environment",
                "TENANT_DB_CREDENTIALS_JSON": json.dumps(self.records),
            },
            clear=False,
        ):
            alpha = secrets_manager.get_tenant_db_credentials("alpha")
            beta = secrets_manager.get_tenant_db_credentials("beta")
        self.assertEqual(alpha["username"], "playschool_alpha")
        self.assertEqual(beta["username"], "playschool_beta")
        self.assertNotEqual(alpha["password"], beta["password"])

    def test_production_never_falls_back_to_local_json(self):
        with patch.dict(
            os.environ,
            {
                "FLASK_ENV": "production",
                "TENANT_CREDENTIAL_PROVIDER": "",
                "TENANT_DB_CREDENTIALS_FILE": str(APP_DIR / ".tenant_secrets.json"),
            },
            clear=False,
        ):
            with self.assertRaises(secrets_manager.CredentialProviderUnavailable):
                secrets_manager.get_tenant_db_credentials("alpha")

    def test_missing_production_environment_credentials_fail_closed(self):
        with patch.dict(
            os.environ,
            {
                "FLASK_ENV": "production",
                "TENANT_CREDENTIAL_PROVIDER": "environment",
                "TENANT_DB_CREDENTIALS_JSON": "{}",
            },
            clear=False,
        ):
            with self.assertRaises(secrets_manager.CredentialProviderUnavailable):
                secrets_manager.get_tenant_db_credentials("alpha")


class CeleryTenantContextTests(unittest.TestCase):
    def test_context_is_explicit_and_sequential_jobs_do_not_share_state(self):
        job_a = make_tenant_job_ref("alpha", "job-a")
        job_b = make_tenant_job_ref("beta", "job-b")
        self.assertEqual(validate_tenant_job_ref(job_a, "alpha")["subdomain"], "alpha")
        self.assertEqual(validate_tenant_job_ref(job_b, "beta")["subdomain"], "beta")
        with self.assertRaises(TenantJobContextError):
            validate_tenant_job_ref(job_a, "beta")
        with self.assertRaises(TenantJobContextError):
            validate_tenant_job_ref({"job_id": "job-c"})

    def test_job_reference_is_checked_against_control_mapping(self):
        ref = make_tenant_job_ref("alpha", "job-a")
        record = resolve_tenant_job_ref(
            ref,
            lambda subdomain: {"subdomain": subdomain, "subscription_status": "active"},
        )
        self.assertEqual(record["subdomain"], "alpha")
        with self.assertRaises(TenantJobContextError):
            resolve_tenant_job_ref(ref, lambda subdomain: None)


class ConfirmedIdorGuardTests(unittest.TestCase):
    def test_confirmed_ownership_guards_are_present_in_live_app(self):
        source = (APP_DIR / "app.py").read_text(encoding="utf-8")
        self.assertIn("WHERE id=%s AND school_id=%s", source)
        self.assertIn("WHERE id=%s AND teacher_id=%s", source)
        self.assertIn("u.school_id=%s AND (h.class_level=%s OR h.class_level='all')", source)
        self.assertIn("role='student' AND class_level=%s AND school_id=%s", source)


if __name__ == "__main__":
    unittest.main()
