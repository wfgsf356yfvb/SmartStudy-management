"""Checksum-verified backup/restore helpers for private local uploads.

This covers the Phase 4 local private-storage backend. S3 backup scheduling and
off-host retention remain deployment/Phase 6 responsibilities.
"""

import hashlib
import json
import os
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from tenant_services.file_storage import is_private_storage_key
from tenant_services.middleware.tenant_resolver import validate_subdomain


def backup_private_uploads_to_s3(tenant_subdomain, bucket, root=None, prefix='private-uploads'):
    """Create a checksum manifest archive and upload it to protected S3."""
    tenant = validate_subdomain(tenant_subdomain)
    if not bucket or not isinstance(bucket, str):
        raise ValueError('An off-host backup bucket is required.')
    try:
        import boto3
    except Exception as exc:
        raise RuntimeError('Off-host backup provider is unavailable.') from exc
    descriptor, temporary_name = tempfile.mkstemp(prefix='.private-upload-backup-', suffix='.zip')
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        provider = os.environ.get('FILE_STORAGE_PROVIDER', 'local').strip().lower()
        if provider == 'local':
            create_private_upload_backup(tenant, temporary, root=root)
        elif provider == 's3':
            source_bucket = os.environ.get('OBJECT_STORAGE_BUCKET', '').strip()
            if not source_bucket or source_bucket == bucket:
                raise ValueError('A distinct source and off-host backup bucket are required.')
            create_s3_upload_backup(tenant, source_bucket, temporary)
        else:
            raise ValueError('Unsupported upload backup storage provider.')
        key = f'{prefix.rstrip("/")}/tenant/{tenant}/{datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")}.zip'
        boto3.client('s3').upload_file(
            str(temporary), bucket, key,
            ExtraArgs={'ServerSideEncryption': 'AES256'},
        )
        return {'bucket': bucket, 'key': key, 'sha256': _checksum(temporary), 'tenant': tenant}
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _root(root=None):
    return Path(root or os.environ.get('PRIVATE_UPLOAD_FOLDER', '') or Path(__file__).resolve().parents[1] / 'instance' / 'private_uploads').resolve()


def _checksum(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def create_private_upload_backup(tenant_subdomain, destination, root=None):
    tenant = validate_subdomain(tenant_subdomain)
    source_root = _root(root)
    tenant_root = source_root / 'tenant' / tenant
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = []
    with tempfile.NamedTemporaryFile(prefix='.upload-backup-', suffix='.zip', delete=False, dir=str(destination.parent)) as temp:
        temporary = Path(temp.name)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            if tenant_root.exists():
                for path in sorted(tenant_root.rglob('*')):
                    if path.is_file():
                        key = '/'.join(path.relative_to(source_root).parts)
                        if not is_private_storage_key(key, tenant):
                            raise ValueError('Unexpected private upload key.')
                        manifest.append({'key': key, 'sha256': _checksum(path), 'size': path.stat().st_size})
                        archive.write(path, key)
            archive.writestr('manifest.json', json.dumps({'tenant': tenant, 'files': manifest}, sort_keys=True))
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return manifest


def create_s3_upload_backup(tenant_subdomain, bucket, destination):
    """Create a checksum manifest archive from one tenant S3 prefix."""
    tenant = validate_subdomain(tenant_subdomain)
    try:
        import boto3
    except Exception as exc:
        raise RuntimeError('Object storage backup provider is unavailable.') from exc
    client = boto3.client('s3')
    destination = Path(destination).resolve()
    manifest = []
    token = None
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        while True:
            request = {'Bucket': bucket, 'Prefix': f'tenant/{tenant}/'}
            if token:
                request['ContinuationToken'] = token
            response = client.list_objects_v2(**request)
            for item in response.get('Contents', []):
                key = item.get('Key', '')
                if not is_private_storage_key(key, tenant):
                    raise ValueError('Unexpected private upload key in object storage.')
                data = client.get_object(Bucket=bucket, Key=key)['Body'].read()
                digest = hashlib.sha256(data).hexdigest()
                manifest.append({'key': key, 'sha256': digest, 'size': len(data)})
                archive.writestr(key, data)
            if not response.get('IsTruncated'):
                break
            token = response.get('NextContinuationToken')
            if not token:
                raise RuntimeError('Object storage backup listing is incomplete.')
        archive.writestr('manifest.json', json.dumps({'tenant': tenant, 'files': manifest}, sort_keys=True))
    return manifest


def restore_private_upload_backup(tenant_subdomain, backup, root=None):
    tenant = validate_subdomain(tenant_subdomain)
    destination_root = _root(root)
    restored = []
    pending = []
    with zipfile.ZipFile(backup, 'r') as archive:
        try:
            manifest = json.loads(archive.read('manifest.json'))
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError('Private upload backup manifest is invalid.') from exc
        if manifest.get('tenant') != tenant or not isinstance(manifest.get('files'), list):
            raise ValueError('Private upload backup tenant is invalid.')
        for item in manifest['files']:
            key = item.get('key', '')
            if not is_private_storage_key(key, tenant) or key not in archive.namelist():
                raise ValueError('Private upload backup contains an unsafe key.')
            data = archive.read(key)
            if hashlib.sha256(data).hexdigest() != item.get('sha256') or len(data) != int(item.get('size', -1)):
                raise ValueError('Private upload backup checksum validation failed.')
            target = (destination_root / key).resolve()
            if destination_root not in target.parents:
                raise ValueError('Private upload restore path is unsafe.')
            if target.exists() and target.read_bytes() != data:
                raise ValueError('Private upload restore would overwrite different data.')
            pending.append((key, target, data))
    written = []
    try:
        for key, target, data in pending:
            if target.exists():
                restored.append(key)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f'.{target.name}.restore')
            with open(temporary, 'wb') as handle:
                handle.write(data)
            os.replace(temporary, target)
            written.append(target)
            if os.name != 'nt':
                os.chmod(target, 0o600)
            restored.append(key)
    except Exception:
        for target in written:
            try:
                target.unlink()
            except OSError:
                pass
        raise
    return restored
