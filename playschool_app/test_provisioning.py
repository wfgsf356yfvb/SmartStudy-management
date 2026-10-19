"""Focused tests for the Phase 3 provisioning workflow."""

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from tenant_services.secrets_manager import (  # noqa: E402
    CredentialNotFound,
    CredentialProviderUnavailable,
    get_tenant_db_credentials,
    store_tenant_db_credentials,
)
from tenant_services.job_context import (  # noqa: E402
    TenantJobContextError,
    validate_tenant_job_ref,
)
from scripts.audit import redact_error  # noqa: E402
from scripts.provision_tenant import (  # noqa: E402
    _account_host,
    _create_tenant_user,
    _grant_config,
    _identifier,
    _validated_tenant_database_name,
    create_tenant_school,
    ProvisioningError,
    tenant_database_name,
    tenant_database_username,
)


class CredentialProviderTests(unittest.TestCase):
    def test_protected_file_keeps_tenant_credentials_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'tenant-credentials.json')
            with patch.dict(os.environ, {
                'FLASK_ENV': 'production',
                'TENANT_CREDENTIAL_PROVIDER': 'protected_file',
                'TENANT_DB_CREDENTIALS_FILE': path,
            }, clear=False):
                store_tenant_db_credentials('alpha', {'database': 'db_a', 'username': 'u_a', 'password': 'p_a'})
                store_tenant_db_credentials('beta', {'database': 'db_b', 'username': 'u_b', 'password': 'p_b'})
                self.assertEqual(get_tenant_db_credentials('alpha')['database'], 'db_a')
                self.assertEqual(get_tenant_db_credentials('beta')['database'], 'db_b')
                self.assertNotEqual(get_tenant_db_credentials('alpha')['password'], 'p_b')
                if os.name != 'nt':
                    self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def test_default_json_name_is_not_a_production_provider(self):
        with patch.dict(os.environ, {
            'FLASK_ENV': 'production',
            'TENANT_CREDENTIAL_PROVIDER': 'protected_file',
            'TENANT_DB_CREDENTIALS_FILE': '.tenant_secrets.json',
        }, clear=False):
            with self.assertRaises(CredentialProviderUnavailable):
                get_tenant_db_credentials('alpha')

    def test_missing_production_credentials_fail_closed(self):
        with patch.dict(os.environ, {
            'FLASK_ENV': 'production',
            'TENANT_CREDENTIAL_PROVIDER': 'environment',
            'TENANT_DB_CREDENTIALS_JSON': json.dumps({}),
        }, clear=False):
            with self.assertRaises(CredentialNotFound):
                get_tenant_db_credentials('alpha')


class ProvisioningSafetyTests(unittest.TestCase):
    def test_tenant_school_mapping_is_created_after_schema_setup(self):
        from unittest.mock import MagicMock
        conn = MagicMock()
        cursor = conn.cursor.return_value
        with patch.dict(os.environ, {
            'PROVISIONING_MYSQL_USER': 'smartstudy_provisioner',
            'PROVISIONING_MYSQL_PASSWORD': 'provisioner-local-only',
            'MYSQL_HOST': 'localhost',
            'MYSQL_PORT': '3306',
        }, clear=False), patch(
            'scripts.provision_tenant.mysql.connector.connect', return_value=conn,
        ) as connect:
            create_tenant_school(
                'playschool_tenant_alpha', 7, 'Alpha School', 'Address', 'alpha',
            )

        self.assertEqual(connect.call_args.kwargs['database'], 'playschool_tenant_alpha')
        sql = cursor.execute.call_args.args[0]
        self.assertIn('INSERT INTO schools', sql)
        self.assertIn('subdomain', sql)
        self.assertEqual(cursor.execute.call_args.args[1], (7, 'Alpha School', 'Address', 'alpha'))
        conn.commit.assert_called_once_with()

    def test_grant_connection_is_separate_and_exactly_scoped(self):
        from unittest.mock import MagicMock
        admin_conn = MagicMock()
        grant_conn = MagicMock()
        admin_cursor = admin_conn.cursor.return_value
        grant_cursor = grant_conn.cursor.return_value
        with patch.dict(os.environ, {
            'PROVISIONING_MYSQL_USER': 'smartstudy_provisioner',
            'PROVISIONING_MYSQL_PASSWORD': 'provisioner-local-only',
            'TENANT_GRANT_MYSQL_USER': 'smartstudy_tenant_granter',
            'TENANT_GRANT_MYSQL_PASSWORD': 'granter-local-only',
            'MYSQL_HOST': 'localhost',
            'MYSQL_PORT': '3306',
        }, clear=False), patch(
            'scripts.provision_tenant.mysql.connector.connect',
            side_effect=[admin_conn, grant_conn],
        ) as connect:
            _create_tenant_user(
                'playschool_tenant_alpha', 'playschool_alpha',
                'generated-local-only', 'localhost',
            )

        self.assertEqual(connect.call_count, 2)
        self.assertEqual(connect.call_args_list[0].kwargs['user'], 'smartstudy_provisioner')
        self.assertEqual(connect.call_args_list[1].kwargs['user'], 'smartstudy_tenant_granter')
        grant_sql = grant_cursor.execute.call_args.args[0]
        self.assertIn('GRANT SELECT, INSERT, UPDATE, DELETE', grant_sql)
        self.assertNotIn('ALL PRIVILEGES', grant_sql)
        self.assertNotIn('GRANT OPTION', grant_sql)

    def test_grant_account_requires_distinct_non_root_credentials(self):
        with patch.dict(os.environ, {
            'PROVISIONING_MYSQL_USER': 'smartstudy_provisioner',
            'PROVISIONING_MYSQL_PASSWORD': 'provisioner-local-only',
            'TENANT_GRANT_MYSQL_USER': 'smartstudy_provisioner',
            'TENANT_GRANT_MYSQL_PASSWORD': 'granter-local-only',
        }, clear=False):
            with self.assertRaises(ProvisioningError):
                _grant_config()
        with patch.dict(os.environ, {
            'PROVISIONING_MYSQL_USER': 'smartstudy_provisioner',
            'PROVISIONING_MYSQL_PASSWORD': 'provisioner-local-only',
            'TENANT_GRANT_MYSQL_USER': 'root',
            'TENANT_GRANT_MYSQL_PASSWORD': 'granter-local-only',
        }, clear=False):
            with self.assertRaises(ProvisioningError):
                _grant_config()

    def test_missing_grant_credentials_fail_closed(self):
        with patch.dict(os.environ, {
            'TENANT_GRANT_MYSQL_USER': '',
            'TENANT_GRANT_MYSQL_PASSWORD': '',
        }, clear=False):
            with self.assertRaises(ProvisioningError):
                _grant_config()

    def test_account_creation_error_is_generic_and_chained(self):
        from unittest.mock import MagicMock
        admin_conn = MagicMock()
        grant_conn = MagicMock()
        grant_conn.cursor.return_value.execute.side_effect = RuntimeError('password=must-not-return')
        with patch.dict(os.environ, {
            'PROVISIONING_MYSQL_USER': 'smartstudy_provisioner',
            'PROVISIONING_MYSQL_PASSWORD': 'provisioner-local-only',
            'TENANT_GRANT_MYSQL_USER': 'smartstudy_tenant_granter',
            'TENANT_GRANT_MYSQL_PASSWORD': 'granter-local-only',
        }, clear=False), patch(
            'scripts.provision_tenant.mysql.connector.connect',
            side_effect=[admin_conn, grant_conn],
        ):
            with self.assertRaisesRegex(ProvisioningError, 'Tenant database account could not be created') as ctx:
                _create_tenant_user('playschool_tenant_alpha', 'playschool_alpha', 'local-only', 'localhost')
        self.assertIsNotNone(ctx.exception.__cause__)
        self.assertNotIn('must-not-return', str(ctx.exception))

    def test_production_compose_keeps_grant_credentials_worker_only(self):
        compose = (APP_DIR / 'docker-compose.production.yml').read_text(encoding='utf-8')
        web = compose.split('  web:', 1)[1].split('  worker:', 1)[0]
        scheduler = compose.split('  scheduler:', 1)[1]
        worker = compose.split('  worker:', 1)[1].split('  scheduler:', 1)[0]
        self.assertNotIn('TENANT_GRANT_MYSQL_', web)
        self.assertNotIn('TENANT_GRANT_MYSQL_', scheduler)
        self.assertIn('TENANT_GRANT_MYSQL_USER', worker)
        self.assertIn('TENANT_GRANT_MYSQL_PASSWORD', worker)

    def test_connection_diagnostic_redacts_secret_like_values(self):
        output = redact_error('password=hidden secret:also-hidden api_key=not-shown')
        self.assertNotIn('hidden', output)
        self.assertNotIn('also-hidden', output)
        self.assertNotIn('not-shown', output)
        self.assertIn('[redacted]', output)

    def test_hyphenated_subdomain_names_are_deterministic_mysql_identifiers(self):
        self.assertEqual(tenant_database_name('tenant-a'), 'playschool_tenant_tenant_a')
        self.assertEqual(tenant_database_username('tenant-a'), 'playschool_tenant_a')
        self.assertEqual(tenant_database_username('tenant-a'), tenant_database_username('tenant-a'))

    def test_overlong_generated_mysql_username_is_rejected_before_provisioning(self):
        from scripts import provision_tenant as module
        subdomain = 'a' * 23
        with patch.dict(os.environ, {'TENANT_DB_USER_HOST': 'localhost'}, clear=False), \
             patch.object(module, 'insert_control_school') as insert_control, \
             patch.object(module, 'create_database_for') as create_database, \
             patch.object(module, '_create_tenant_user') as create_user:
            result = module.provision_tenant('Local', subdomain)
        self.assertFalse(result['success'])
        self.assertIn('MySQL username that is too long', result['message'])
        insert_control.assert_not_called()
        create_database.assert_not_called()
        create_user.assert_not_called()

    def test_overlong_username_returns_sanitized_provisioning_failure(self):
        from scripts import provision_tenant as module
        with patch.dict(os.environ, {'TENANT_DB_USER_HOST': 'localhost'}, clear=False):
            result = module.provision_tenant('Local', 'a' * 23)
        self.assertFalse(result['success'])
        self.assertEqual(result['message'], 'Tenant subdomain produces a MySQL username that is too long.')

    def test_omitted_db_uses_canonical_name(self):
        self.assertEqual(
            _validated_tenant_database_name('tenant-a'),
            'playschool_tenant_tenant_a',
        )

    def test_matching_explicit_db_passes_canonical_validation(self):
        self.assertEqual(
            _validated_tenant_database_name('tenant-a', 'playschool_tenant_tenant_a'),
            'playschool_tenant_tenant_a',
        )

    def test_unrelated_explicit_db_is_rejected_before_provisioning(self):
        from scripts import provision_tenant as module
        with patch.object(module, 'insert_control_school') as insert_control, \
             patch.object(module, 'create_database_for') as create_database, \
             patch.object(module, '_create_tenant_user') as create_user:
            with self.assertRaisesRegex(ProvisioningError, 'canonical subdomain-derived'):
                module.provision_tenant(
                    'Local', 'tenant-a', dbname='playschool_tenant_other'
                )
        insert_control.assert_not_called()
        create_database.assert_not_called()
        create_user.assert_not_called()

    def test_invalid_explicit_db_is_rejected_before_provisioning(self):
        from scripts import provision_tenant as module
        with patch.object(module, 'insert_control_school') as insert_control, \
             patch.object(module, 'create_database_for') as create_database, \
             patch.object(module, '_create_tenant_user') as create_user:
            with self.assertRaises(ProvisioningError):
                module.provision_tenant('Local', 'tenant-a', dbname='bad.name')
        insert_control.assert_not_called()
        create_database.assert_not_called()
        create_user.assert_not_called()

    def test_normalized_names_remain_strictly_validated(self):
        with self.assertRaises(ProvisioningError):
            _identifier('tenant.a', 'tenant identifier')
        with self.assertRaises(ValueError):
            tenant_database_username('tenant.a')

    def test_job_context_cannot_be_reassigned_to_another_job(self):
        with self.assertRaises(TenantJobContextError):
            validate_tenant_job_ref(
                {'job_id': 'job-a', 'subdomain': 'alpha'},
                expected_subdomain='alpha', expected_job_id='job-b',
            )

    def test_provisioning_source_has_no_wildcard_or_all_privileges_grant(self):
        source = (APP_DIR / 'scripts' / 'provision_tenant.py').read_text(encoding='utf-8')
        self.assertNotIn("@'%'", source)
        self.assertNotIn('ALL PRIVILEGES', source)
        self.assertIn("user.lower() == 'root'", source)

    def test_tenant_account_host_requires_private_scoped_policy(self):
        with patch.dict(os.environ, {'TENANT_DB_USER_HOST': '172.20.%'}, clear=False):
            self.assertEqual(_account_host(), '172.20.%')
        with patch.dict(os.environ, {'TENANT_DB_USER_HOST': '%'}, clear=False):
            with self.assertRaises(ProvisioningError):
                _account_host()
        with patch.dict(os.environ, {'TENANT_DB_USER_HOST': ''}, clear=False):
            with self.assertRaises(ProvisioningError):
                _account_host()

    def test_provider_selection_is_not_mutated_by_job_option(self):
        source = (APP_DIR / 'scripts' / 'provision_tenant.py').read_text(encoding='utf-8')
        self.assertNotIn("os.environ['TENANT_CREDENTIAL_PROVIDER'] = 'aws'", source)
        self.assertIn('credential-provider option does not match server configuration', source)

    def test_provisioning_rejects_inactive_job_context(self):
        ref = {'job_id': 'job-a', 'subdomain': 'alpha'}
        with self.assertRaises(TenantJobContextError):
            from tenant_services.job_context import resolve_tenant_job_ref
            resolve_tenant_job_ref(ref, lambda _: {'subdomain': 'alpha', 'subscription_status': 'provisioning'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
