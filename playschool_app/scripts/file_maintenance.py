"""Supervised, tenant-scoped Phase 4 retention and backup tasks."""

import json
import os

import mysql.connector

from scripts.audit import log as audit_log, redact_error
from scripts.celery_app import celery_app
from scripts.private_upload_backup import backup_private_uploads_to_s3
from tenant_services.file_storage import purge_expired_uploads
from tenant_services.job_context import resolve_tenant_job_ref


def _control_lookup(subdomain):
    config = {
        'host': os.environ.get('MYSQL_HOST', 'localhost'),
        'port': int(os.environ.get('MYSQL_PORT', 3306)),
        'database': os.environ.get('MYSQL_DB', ''),
        'user': os.environ.get('MYSQL_USER', ''),
        'password': os.environ.get('MYSQL_PASSWORD', ''),
    }
    if not config['database'] or not config['user'] or not config['password']:
        raise RuntimeError('Control database configuration is unavailable.')
    connection = mysql.connector.connect(**config)
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            'SELECT id, subdomain, subscription_status FROM schools WHERE subdomain=%s',
            (subdomain,),
        )
        return cursor.fetchone()
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        connection.close()


@celery_app.task(bind=True, autoretry_for=(RuntimeError,), retry_backoff=True, max_retries=3)
def maintain_tenant_files(self, tenant_ref):
    """Validate one server-generated tenant reference before maintenance."""
    try:
        tenant = resolve_tenant_job_ref(tenant_ref, _control_lookup)
        subdomain = tenant['subdomain']
        deleted = purge_expired_uploads(subdomain, dry_run=False)
        bucket = os.environ.get('UPLOAD_BACKUP_BUCKET', '').strip()
        if not bucket:
            raise RuntimeError('UPLOAD_BACKUP_BUCKET is required for off-host upload backups.')
        backup = backup_private_uploads_to_s3(
            subdomain,
            bucket,
            prefix=os.environ.get('UPLOAD_BACKUP_PREFIX', 'private-uploads'),
        )
        result = {'tenant': subdomain, 'deleted_count': len(deleted), 'backup': backup}
        audit_log('tenant_file_maintenance_completed', {
            'tenant': subdomain,
            'deleted_count': len(deleted),
            'backup_key': backup['key'],
        })
        return result
    except Exception as exc:
        safe_error = redact_error(exc)
        audit_log('tenant_file_maintenance_failed', {
            'tenant': (tenant_ref or {}).get('subdomain') if isinstance(tenant_ref, dict) else None,
            'message': safe_error,
        })
        raise RuntimeError(safe_error) from exc


@celery_app.task
def run_configured_file_maintenance():
    """Enqueue only explicit server-configured tenant references."""
    raw = os.environ.get('FILE_MAINTENANCE_TENANTS_JSON', '').strip()
    if not raw:
        raise RuntimeError('FILE_MAINTENANCE_TENANTS_JSON is required for scheduled maintenance.')
    try:
        references = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError('FILE_MAINTENANCE_TENANTS_JSON is invalid.') from exc
    if not isinstance(references, list):
        raise RuntimeError('FILE_MAINTENANCE_TENANTS_JSON must be a JSON list.')

    if not references:
        return {'enqueued': []}
    jobs = []
    for reference in references:
        if not isinstance(reference, dict) or not reference.get('job_id') or not reference.get('subdomain'):
            raise RuntimeError('Scheduled maintenance contains invalid tenant context.')
        jobs.append(maintain_tenant_files.delay(reference).id)
    return {'enqueued': jobs}
