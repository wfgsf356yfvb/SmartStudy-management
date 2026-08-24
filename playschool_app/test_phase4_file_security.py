"""Phase 4 private-storage and upload-validation tests."""

import io
import os
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from werkzeug.datastructures import FileStorage

from tenant_services.file_storage import (
    UploadValidationError,
    UploadQuotaExceeded,
    UploadScanFailed,
    is_private_storage_key,
    save_private_upload,
    purge_expired_uploads,
)
import tenant_services.file_storage as file_storage
from scripts.migrate_legacy_uploads import migrate_legacy_file, rollback_legacy_migration
from scripts.private_upload_backup import create_private_upload_backup, restore_private_upload_backup


class PrivateStorageTests(unittest.TestCase):
    def test_s3_quota_listing_is_paginated_and_tenant_scoped(self):
        class FakeS3:
            def __init__(self):
                self.calls = []

            def list_objects_v2(self, **kwargs):
                self.calls.append(kwargs)
                if len(self.calls) == 1:
                    return {
                        'Contents': [{'Key': 'tenant/school-a/payment/a.pdf', 'Size': 10}],
                        'IsTruncated': True,
                        'NextContinuationToken': 'next',
                    }
                return {
                    'Contents': [{'Key': 'tenant/school-a/payment/b.pdf', 'Size': 15}],
                    'IsTruncated': False,
                }

        fake = FakeS3()
        with patch.object(file_storage, '_s3_client', return_value=fake), patch.dict(
            os.environ, {'OBJECT_STORAGE_BUCKET': 'private-bucket'}, clear=False
        ):
            self.assertEqual(file_storage._s3_usage('school-a'), 25)
        self.assertEqual(fake.calls[1].get('ContinuationToken'), 'next')

    def test_upload_gets_immutable_tenant_prefixed_key(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {'PRIVATE_UPLOAD_FOLDER': directory, 'FLASK_ENV': 'development', 'ALLOW_UNSCANNED_UPLOADS': '1', 'FILE_SCANNER_PROVIDER': 'disabled'},
            clear=False,
        ):
            upload = FileStorage(
                stream=io.BytesIO(b'%PDF-1.7\nprivate test'),
                filename='../receipt.pdf',
                content_type='application/pdf',
            )
            key = save_private_upload(upload, 'school-a', 'payment', {'pdf'})
            self.assertRegex(key, r'^tenant/school-a/payment/[A-Za-z0-9_-]+\.pdf$')
            self.assertTrue(os.path.isfile(os.path.join(directory, *key.split('/'))))
            self.assertTrue(is_private_storage_key(key, 'school-a'))
            self.assertFalse(is_private_storage_key(key, 'school-b'))

    def test_invalid_content_and_traversal_keys_are_rejected(self):
        upload = FileStorage(stream=io.BytesIO(b'not a pdf'), filename='x.pdf')
        with self.assertRaises(UploadValidationError):
            save_private_upload(upload, 'school-a', 'payment', {'pdf'})
        self.assertFalse(is_private_storage_key('tenant/school-a/../secret.pdf'))
        self.assertFalse(is_private_storage_key('../../secret.pdf'))

    def test_browser_mime_type_cannot_enable_disallowed_extension(self):
        upload = FileStorage(
            stream=io.BytesIO(b'%PDF-1.7\nprivate test'),
            filename='x.exe',
            content_type='application/pdf',
        )
        with self.assertRaises(UploadValidationError):
            save_private_upload(upload, 'school-a', 'payment', {'pdf'})

    def test_production_rejects_unscanned_uploads(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {'PRIVATE_UPLOAD_FOLDER': directory, 'FLASK_ENV': 'production', 'FILE_SCANNER_PROVIDER': 'disabled'},
            clear=False,
        ):
            upload = FileStorage(stream=io.BytesIO(b'%PDF-1.7\nprivate test'), filename='x.pdf')
            with self.assertRaises(UploadScanFailed):
                save_private_upload(upload, 'school-a', 'payment', {'pdf'})

    def test_tenant_quota_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {'PRIVATE_UPLOAD_FOLDER': directory, 'FLASK_ENV': 'development',
             'ALLOW_UNSCANNED_UPLOADS': '1', 'FILE_SCANNER_PROVIDER': 'disabled', 'TENANT_UPLOAD_QUOTA_BYTES': '5'},
            clear=False,
        ):
            upload = FileStorage(stream=io.BytesIO(b'%PDF-1.7\nprivate test'), filename='x.pdf')
            with self.assertRaises(UploadQuotaExceeded):
                save_private_upload(upload, 'school-a', 'payment', {'pdf'})

    def test_s3_provider_uploads_private_key_without_local_fallback(self):
        class FakeS3:
            def __init__(self):
                self.uploads = []

            def list_objects_v2(self, **kwargs):
                return {'Contents': []}

            def upload_fileobj(self, stream, bucket, key, ExtraArgs):
                self.uploads.append((bucket, key, stream.read(), ExtraArgs))

        fake = FakeS3()
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {'PRIVATE_UPLOAD_FOLDER': directory, 'FLASK_ENV': 'development',
             'ALLOW_UNSCANNED_UPLOADS': '1', 'FILE_SCANNER_PROVIDER': 'disabled', 'FILE_STORAGE_PROVIDER': 's3',
             'OBJECT_STORAGE_BUCKET': 'private-bucket'},
            clear=False,
        ), patch('tenant_services.file_storage._s3_client', return_value=fake):
            upload = FileStorage(stream=io.BytesIO(b'%PDF-1.7\nprivate test'), filename='x.pdf')
            key = save_private_upload(upload, 'school-a', 'payment', {'pdf'})
            self.assertTrue(key.startswith('tenant/school-a/payment/'))
            self.assertEqual(fake.uploads[0][0], 'private-bucket')
            self.assertFalse(os.path.exists(os.path.join(directory, *key.split('/'))))

    def test_private_upload_backup_restore_is_checksum_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, 'private')
            key = 'tenant/school-a/payment/file.pdf'
            path = os.path.join(root, *key.split('/'))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as handle:
                handle.write(b'%PDF-1.7\nprivate test')
            backup = os.path.join(directory, 'uploads.zip')
            manifest = create_private_upload_backup('school-a', backup, root=root)
            os.unlink(path)
            self.assertEqual(restore_private_upload_backup('school-a', backup, root=root), [key])
            self.assertEqual(manifest[0]['size'], os.path.getsize(path))

    def test_legacy_migration_requires_one_owner_and_supports_rollback(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {'FLASK_ENV': 'development', 'ALLOW_UNSCANNED_UPLOADS': '1', 'FILE_SCANNER_PROVIDER': 'disabled'}, clear=False
        ):
            legacy = os.path.join(directory, 'legacy')
            private = os.path.join(directory, 'private')
            os.makedirs(legacy)
            with open(os.path.join(legacy, 'old.pdf'), 'wb') as handle:
                handle.write(b'%PDF-1.7\nprivate test')
            updates = []

            def query(sql, args):
                return [{'id': 7}] if 'homework' in sql else []

            def update(table, column, row_id, value):
                updates.append((table, column, row_id, value))

            manifest_path = os.path.join(directory, 'migration.json')
            manifest = migrate_legacy_file('old.pdf', 'school-a', legacy, private, query, update, manifest_path)
            self.assertEqual(manifest['owner']['table'], 'homework')
            rollback_legacy_migration(manifest_path, private, update)
            self.assertEqual(updates[-1][-1], 'old.pdf')
            self.assertFalse(os.path.exists(os.path.join(private, *manifest['key'].split('/'))))

    def test_legacy_migration_is_idempotent_and_recovery_removes_partial_copy(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {'FLASK_ENV': 'development', 'ALLOW_UNSCANNED_UPLOADS': '1', 'FILE_SCANNER_PROVIDER': 'disabled'}, clear=False
        ):
            legacy = os.path.join(directory, 'legacy')
            private = os.path.join(directory, 'private')
            os.makedirs(legacy)
            with open(os.path.join(legacy, 'old.pdf'), 'wb') as handle:
                handle.write(b'%PDF-1.7\nprivate test')
            updates = []

            def query(sql, args):
                return [{'id': 7}] if 'homework' in sql else []

            def update(table, column, row_id, value):
                updates.append(value)

            manifest_path = os.path.join(directory, 'migration.json')
            first = migrate_legacy_file('old.pdf', 'school-a', legacy, private, query, update, manifest_path)
            second = migrate_legacy_file('old.pdf', 'school-a', legacy, private, query, update, manifest_path)
            self.assertEqual(first, second)
            self.assertEqual(len(updates), 1)

            with open(os.path.join(legacy, 'broken.pdf'), 'wb') as handle:
                handle.write(b'%PDF-1.7\nbroken')
            broken_manifest = os.path.join(directory, 'broken.json')

            def failing_update(table, column, row_id, value):
                if value != 'broken.pdf':
                    raise RuntimeError('simulated control update failure')

            with self.assertRaises(RuntimeError):
                migrate_legacy_file('broken.pdf', 'school-a', legacy, private, query, failing_update, broken_manifest)
            self.assertFalse(os.path.exists(broken_manifest))
            legacy_objects = list(os.scandir(os.path.join(private, 'tenant', 'school-a', 'legacy')))
            self.assertEqual(len(legacy_objects), 1)

    def test_retention_deletes_only_expired_tenant_objects(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {'PRIVATE_UPLOAD_FOLDER': directory, 'FILE_STORAGE_PROVIDER': 'local', 'UPLOAD_RETENTION_DAYS': '7'},
            clear=False,
        ):
            old_path = os.path.join(directory, 'tenant', 'school-a', 'payment', 'old.pdf')
            new_path = os.path.join(directory, 'tenant', 'school-a', 'payment', 'new.pdf')
            other_path = os.path.join(directory, 'tenant', 'school-b', 'payment', 'old.pdf')
            for path in (old_path, new_path, other_path):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'wb') as handle:
                    handle.write(b'%PDF-1.7\nprivate')
            old_time = (datetime.now(timezone.utc) - timedelta(days=8)).timestamp()
            os.utime(old_path, (old_time, old_time))
            self.assertEqual(purge_expired_uploads('school-a', dry_run=True), ['tenant/school-a/payment/old.pdf'])
            purge_expired_uploads('school-a', dry_run=False)
            self.assertFalse(os.path.exists(old_path))
            self.assertTrue(os.path.exists(new_path))
            self.assertTrue(os.path.exists(other_path))

    def test_backup_restore_rejects_wrong_tenant_and_tampered_content_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, 'private')
            key_a = 'tenant/school-a/payment/a.pdf'
            key_b = 'tenant/school-a/payment/b.pdf'
            for key in (key_a, key_b):
                path = os.path.join(root, *key.split('/'))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'wb') as handle:
                    handle.write(b'%PDF-1.7\n' + key.encode())
            backup = os.path.join(directory, 'uploads.zip')
            create_private_upload_backup('school-a', backup, root=root)
            with self.assertRaises(ValueError):
                restore_private_upload_backup('school-b', backup, root=os.path.join(directory, 'restore'))

            import zipfile
            tampered = os.path.join(directory, 'tampered.zip')
            with zipfile.ZipFile(backup, 'r') as source, zipfile.ZipFile(tampered, 'w') as target:
                for name in source.namelist():
                    data = source.read(name)
                    if name == key_b:
                        data += b'tampered'
                    target.writestr(name, data)
            restore_root = os.path.join(directory, 'restore')
            with self.assertRaises(ValueError):
                restore_private_upload_backup('school-a', tampered, root=restore_root)
            self.assertFalse(os.path.exists(restore_root))

    def test_production_rejects_public_storage_and_disabled_scanning(self):
        env = os.environ.copy()
        env.update({
            'FLASK_ENV': 'production', 'SECRET_KEY': 'phase4-test-secret-012345678901234567890123',
            'MYSQL_USER': 'phase4_app', 'MYSQL_PASSWORD': 'phase4-password',
            'TENANT_DB_USER_HOST': '172.20.%',
            'TENANT_BASE_DOMAIN': 'example.com', 'TENANT_CREDENTIAL_PROVIDER': 'environment',
            'TENANT_DB_CREDENTIALS_JSON': '{}', 'FILE_STORAGE_PROVIDER': 'local',
            'PRIVATE_UPLOAD_FOLDER': os.path.join('static', 'uploads'),
            'FILE_SCANNER_PROVIDER': 'disabled', 'FILE_SCANNER_COMMAND': '',
        })
        result = subprocess.run([sys.executable, '-c', 'from config import Config'], cwd=os.path.dirname(__file__), env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue('static/uploads' in result.stderr or 'scanner' in result.stderr.lower())

    def test_download_authorization_denies_cross_tenant_and_unowned_record(self):
        with patch.dict(
            os.environ,
            {'FLASK_ENV': 'development', 'MYSQL_USER': 'phase4_test', 'MYSQL_PASSWORD': 'phase4_test'},
            clear=False,
        ):
            from app import app, file_is_authorized

            with app.test_request_context('/uploads/tenant/school-a/payment/file.pdf'):
                from flask import g, session
                g.tenant = {'subdomain': 'school-a'}
                session.update({'user_id': 11, 'role': 'student', 'school_id': 4})
                with patch('app.current_user', return_value={'id': 11, 'class_level': 'nursery'}), patch(
                    'app.query_db', return_value=None
                ):
                    self.assertFalse(file_is_authorized('tenant/school-a/payment/file.pdf'))
                    self.assertFalse(file_is_authorized('tenant/school-b/payment/file.pdf'))


if __name__ == '__main__':
    unittest.main()
