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
            "TENANT_DB_USER_HOST": "172.20.%",
            "TENANT_BASE_DOMAIN": "example.com",
            "TENANT_CREDENTIAL_PROVIDER": "environment",
            "TENANT_DB_CREDENTIALS_JSON": "{}",
            "FILE_STORAGE_PROVIDER": "local",
            "FILE_SCANNER_PROVIDER": "command",
            "FILE_SCANNER_COMMAND": "scanner-test-placeholder",
            "ALLOW_UNSCANNED_UPLOADS": "0",
            "TENANT_UPLOAD_QUOTA_BYTES": "1048576",
            "UPLOAD_RETENTION_DAYS": "7",
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
        # Other isolation tests may import Config during discovery. Reload the
        # live app/config modules under the explicit production test environment.
        sys.modules.pop('app', None)
        sys.modules.pop('config', None)
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
            APP_DIR / "check_user.py",
            APP_DIR / "create_user_direct.py",
            APP_DIR / "register_and_verify.py",
            APP_DIR / "verify_reset_flow.py",
            APP_DIR / "update_superadmin_email.py",
        ]
        forbidden = (
            "superadmin123",
            "admin123",
            "teacher123",
            "nursery123",
            "lkg123",
            "ukg123",
            "rootpwd",
            "Testpass123",
            "y0263320@gmail.com",
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

    def test_production_profile_excludes_test_broker_and_eager_mode(self):
        compose = (APP_DIR / "docker-compose.production.yml").read_text(encoding="utf-8")
        self.assertNotIn("fakeredis", compose.lower())
        self.assertIn("CELERY_EAGER: \"0\"", compose)
        self.assertIn("REDIS_PASSWORD is required", compose)

    def test_production_source_has_tenant_boundary_and_registration_guards(self):
        source = (APP_DIR / "app.py").read_text(encoding="utf-8")
        self.assertIn("Tenant context is required.", source)
        self.assertIn("if not g.tenant:", source)
        self.assertIn("school_id   = g.tenant['id']", source)
        self.assertIn("Public registration is limited to student accounts.", source)

    def test_production_examples_do_not_contain_copyable_credentials(self):
        example = (APP_DIR / ".env.example").read_text(encoding="utf-8")
        self.assertNotIn("playschool_super_secret_key_2026", example)
        self.assertNotIn("MYSQL_USER=root", example)
        self.assertIn("TENANT_DB_USER_HOST=<private-docker-subnet-pattern>", example)

    def test_production_logging_and_scheduler_are_bounded_and_supervised(self):
        compose = (APP_DIR / "docker-compose.production.yml").read_text(encoding="utf-8")
        self.assertIn("scheduler:", compose)
        self.assertGreaterEqual(compose.count('max-size: "10m"'), 5)
        self.assertIn("UPLOAD_BACKUP_BUCKET is required", compose)

    def test_fee_payment_template_uses_live_endpoint(self):
        template = (APP_DIR / "templates" / "admin" / "fee_payments.html").read_text(encoding="utf-8")
        self.assertIn("url_for('verify_fee_payment'", template)
        self.assertNotIn("url_for('admin_verify_payment'", template)


if __name__ == "__main__":
    unittest.main()
