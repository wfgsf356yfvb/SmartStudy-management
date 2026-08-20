"""Regression tests for the Phase 1 production security lockdown."""

import os
import subprocess
import sys
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent


def production_environment(**overrides):
    environment = os.environ.copy()
    environment.update(
        {
            "FLASK_ENV": "production",
            "SECRET_KEY": "phase1-test-secret-012345678901234567890123",
            "MYSQL_USER": "phase1_app",
            "MYSQL_PASSWORD": "phase1-test-password",
        }
    )
    environment.update(overrides)
    return environment


class ProductionConfigurationTests(unittest.TestCase):
    def run_config_import(self, **overrides):
        return subprocess.run(
            [sys.executable, "-c", "from config import Config; print(Config.IS_PRODUCTION)"],
            cwd=APP_DIR,
            env=production_environment(**overrides),
            capture_output=True,
            text=True,
        )

    def test_production_requires_secret_key(self):
        result = self.run_config_import(SECRET_KEY="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SECRET_KEY", result.stderr)

    def test_production_rejects_root_application_user(self):
        result = self.run_config_import(MYSQL_USER="root")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-root", result.stderr)

    def test_production_requires_database_password(self):
        result = self.run_config_import(MYSQL_PASSWORD="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MYSQL_PASSWORD", result.stderr)


class ProductionSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(APP_DIR))
        os.environ.update(production_environment())
        try:
            from app import app  # pylint: disable=import-outside-toplevel
        except ModuleNotFoundError as error:
            raise unittest.SkipTest(
                f"runtime dependency unavailable: {error.name}"
            ) from error

        cls.app = app

    def test_initialization_and_development_routes_are_not_registered(self):
        routes = {rule.rule for rule in self.app.url_map.iter_rules()}
        self.assertNotIn("/init-db", routes)
        self.assertNotIn("/test", routes)

    def test_initialization_and_development_routes_return_not_found(self):
        client = self.app.test_client()
        self.assertEqual(client.get("/init-db").status_code, 404)
        self.assertEqual(client.get("/test").status_code, 404)


class ProductionArtifactTests(unittest.TestCase):
    def test_runtime_setup_contains_no_audit_confirmed_demo_passwords(self):
        runtime_files = [
            APP_DIR / "app.py",
            APP_DIR / "mysql_setup.py",
            APP_DIR / "schema.sql",
            APP_DIR / "sqlite_schema.sql",
            APP_DIR / "migrate_db.py",
            APP_DIR / "scripts" / "run_migrations.py",
            APP_DIR / "scripts" / "provision_tenant.py",
        ]
        forbidden = (
            "superadmin123",
            "admin123",
            "teacher123",
            "nursery123",
            "lkg123",
            "ukg123",
            "rootpwd",
        )
        for path in runtime_files:
            contents = path.read_text(encoding="utf-8")
            for credential in forbidden:
                self.assertNotIn(credential, contents, f"unsafe credential in {path.name}")

    def test_compose_requires_external_credentials_for_app_services(self):
        compose = (APP_DIR / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertNotIn("MYSQL_USER: root", compose)
        self.assertNotIn("MYSQL_PASSWORD: rootpwd", compose)
        self.assertIn("MYSQL_APP_USER:?MYSQL_APP_USER is required", compose)
        self.assertIn("MYSQL_APP_PASSWORD:?MYSQL_APP_PASSWORD is required", compose)


if __name__ == "__main__":
    unittest.main()
