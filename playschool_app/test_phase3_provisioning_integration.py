"""Opt-in live Phase 3 verification against an isolated MySQL instance.

Run only with PHASE3_LIVE_TEST=1 and temporary test-service credentials. The
test never contains or prints a password and removes its tenant resources in
tearDownClass.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


@unittest.skipUnless(os.environ.get('PHASE3_LIVE_TEST') == '1', 'live Phase 3 test is opt-in')
class LiveProvisioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import mysql.connector

        cls.mysql = mysql.connector
        cls.host = os.environ['MYSQL_HOST']
        cls.port = int(os.environ['MYSQL_PORT'])
        cls.control_db = os.environ['MYSQL_DB']
        cls.admin_user = os.environ['PROVISIONING_MYSQL_USER']
        cls.admin_password = os.environ['PROVISIONING_MYSQL_PASSWORD']
        cls.grant_user = os.environ['TENANT_GRANT_MYSQL_USER']
        cls.grant_password = os.environ['TENANT_GRANT_MYSQL_PASSWORD']
        cls.subdomain = os.environ.get('PHASE3_TEST_SUBDOMAIN', 'phase3-live')
        from scripts.provision_tenant import tenant_database_name, tenant_database_username
        cls.dbname = os.environ.get('PHASE3_TEST_DB', tenant_database_name(cls.subdomain))
        cls.tenant_user = tenant_database_username(cls.subdomain)
        cls.credential_file = os.environ['TENANT_DB_CREDENTIALS_FILE']
        from scripts.provision_tenant import provision_tenant
        cls.provision_tenant = provision_tenant
        cls._ensure_tenant()

    @classmethod
    def _admin_connection(cls, database=None):
        config = {
            'host': cls.host, 'port': cls.port, 'user': cls.admin_user,
            'password': cls.admin_password,
        }
        if database:
            config['database'] = database
        return cls.mysql.connect(**config)

    @classmethod
    def _query(cls, sql, params=(), database=None, dictionary=False):
        conn = cls._admin_connection(database)
        cur = conn.cursor(dictionary=dictionary)
        try:
            cur.execute(sql, params)
            return cur.fetchall()
        finally:
            cur.close()
            conn.close()

    @classmethod
    def _ensure_tenant(cls):
        existing = cls._query('SELECT id FROM schools WHERE subdomain=%s', (cls.subdomain,), cls.control_db)
        if not existing:
            result = cls.provision_tenant('Phase 3 Integration Tenant', cls.subdomain, 'test')
            if not result.get('success'):
                raise AssertionError(result)

    @classmethod
    def tearDownClass(cls):
        try:
            from tenant_services.secrets_manager import delete_tenant_db_credentials
            delete_tenant_db_credentials(cls.subdomain)
        except Exception:
            pass
        try:
            conn = cls._admin_connection()
            cur = conn.cursor()
            cur.execute('DELETE FROM schools WHERE subdomain=%s', (cls.subdomain,))
            conn.commit()
            cur.execute(f"DROP USER IF EXISTS '{cls.tenant_user}'@'localhost'")
            cur.execute(f'DROP DATABASE IF EXISTS `{cls.dbname}`')
            conn.commit()
            cur.close()
            conn.close()
        except Exception:
            pass

    def test_control_mapping_schema_and_exact_tenant_grants(self):
        mapping = self._query(
            'SELECT subdomain FROM schools WHERE subdomain=%s',
            (self.subdomain,), self.control_db,
        )
        self.assertEqual(mapping[0][0], self.subdomain)
        tables = self._query(
            'SELECT table_name FROM information_schema.tables WHERE table_schema=%s',
            (self.dbname,),
        )
        self.assertIn(('schools',), tables)
        grants = '\n'.join(row[0] for row in self._query(
            f"SHOW GRANTS FOR '{self.tenant_user}'@'localhost'"
        ))
        self.assertIn(f'SELECT, INSERT, UPDATE, DELETE ON `{self.dbname}`.*', grants)
        self.assertNotIn('GRANT OPTION', grants)
        self.assertNotIn('ALL PRIVILEGES', grants)
        self.assertNotIn("'%'", grants)
        self.assertNotIn('root', grants.lower())

    def test_resolver_and_runtime_connection_use_tenant_database(self):
        from tenant_services.middleware.tenant_resolver import resolve_tenant, TenantResolutionError
        from tenant_services.tenant_db import get_connection_for_tenant

        def control_query(sql, params, one=False, use_control=False):
            rows = self._query(sql, params, self.control_db, dictionary=True)
            return rows[0] if one and rows else (None if one else rows)

        tenant = resolve_tenant(
            control_query, f'{self.subdomain}.example.test', 'example.test', (80, 443)
        )
        self.assertEqual(tenant['subdomain'], self.subdomain)
        connection = get_connection_for_tenant(tenant)
        try:
            cursor = connection.cursor()
            cursor.execute('SELECT DATABASE(), CURRENT_USER()')
            database, current_user = cursor.fetchone()
            self.assertEqual(database, self.dbname)
            self.assertTrue(current_user.startswith(f'{self.tenant_user}@'))
        finally:
            connection.close()
        with self.assertRaises(TenantResolutionError):
            resolve_tenant(control_query, 'unknown.example.test', 'example.test', (80, 443))

    def test_duplicate_provisioning_is_rejected_without_second_mapping(self):
        result = self.provision_tenant('Duplicate', self.subdomain, 'test')
        self.assertFalse(result['success'])
        self.assertEqual(
            self._query('SELECT COUNT(*) FROM schools WHERE subdomain=%s', (self.subdomain,), self.control_db)[0][0],
            1,
        )

    def test_zz_failed_schema_step_compensates_all_resources(self):
        failure_subdomain = self.subdomain + 'fail'
        from scripts.provision_tenant import tenant_database_name, tenant_database_username
        failure_db = tenant_database_name(failure_subdomain)
        from scripts import provision_tenant as module
        with patch.object(module, 'create_tables_for_db', side_effect=RuntimeError('intentional test failure')):
            result = module.provision_tenant('Rollback', failure_subdomain, 'test')
        self.assertFalse(result['success'])
        self.assertEqual(self._query('SELECT COUNT(*) FROM schools WHERE subdomain=%s', (failure_subdomain,), self.control_db)[0][0], 0)
        self.assertEqual(self._query('SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name=%s', (failure_db,))[0][0], 0)
        self.assertEqual(self._query('SELECT COUNT(*) FROM mysql.user WHERE user=%s', (tenant_database_username(failure_subdomain),))[0][0], 0)
        if os.path.exists(self.credential_file):
            with open(self.credential_file, encoding='utf-8') as handle:
                self.assertNotIn(failure_subdomain, json.load(handle))

    def test_job_status_attempt_timestamp_and_redaction(self):
        from scripts import provision_jobs
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(provision_jobs, 'JOBS_FILE', os.path.join(directory, 'jobs.json')):
                job_id = provision_jobs.create_job({'name': 'test', 'subdomain': self.subdomain})
                provision_jobs.update_job(job_id, status='running')
                provision_jobs.update_job(job_id, status='error', error='password=never-print-this')
                job = provision_jobs.get_job(job_id)
        self.assertEqual(job['attempts'], 1)
        self.assertTrue(job['created_at'])
        self.assertTrue(job['updated_at'])
        self.assertNotIn('never-print-this', job['error'])

    def test_audit_event_contains_status_metadata_only(self):
        from scripts import provision_tenant as module
        with patch.object(module, 'audit_log') as audit:
            result = module.provision_tenant('Duplicate', self.subdomain, 'test')
        self.assertFalse(result['success'])
        self.assertTrue(audit.called)
        event, details = audit.call_args.args
        self.assertEqual(event, 'tenant_provisioning_failed')
        self.assertEqual(details['subdomain'], self.subdomain)
        self.assertNotIn('password', json.dumps(details).lower())


if __name__ == '__main__':
    unittest.main(verbosity=2)
