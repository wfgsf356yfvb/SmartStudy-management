"""Private, tenant-prefixed local file storage for the Phase 4 baseline."""

import os
import re
import secrets
import shlex
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from werkzeug.utils import secure_filename

from tenant_services.middleware.tenant_resolver import validate_subdomain


class UploadValidationError(ValueError):
    """The supplied upload is not safe or is not an allowed file type."""


class StorageProviderUnavailable(RuntimeError):
    """The configured local/object storage provider cannot be used safely."""


class UploadQuotaExceeded(RuntimeError):
    """The tenant has exceeded its configured private-upload quota."""


class UploadScanFailed(UploadValidationError):
    """The scanner did not establish that the upload is clean."""


def _extension(filename):
    safe = secure_filename(filename or '')
    if not safe or '.' not in safe:
        raise UploadValidationError('A file extension is required.')
    return safe, safe.rsplit('.', 1)[1].lower()


def _content_is_valid(stream, extension):
    """Perform lightweight content checks without trusting the browser MIME type."""
    try:
        position = stream.tell()
        header = stream.read(16)
        stream.seek(position)
    except (AttributeError, OSError):
        return False

    if extension in {'jpg', 'jpeg', 'png', 'gif'}:
        try:
            from PIL import Image
            position = stream.tell()
            image = Image.open(stream)
            image.verify()
            stream.seek(position)
            return True
        except Exception:
            try:
                stream.seek(position)
            except (AttributeError, OSError):
                pass
            return False
    if extension == 'pdf':
        return header.startswith(b'%PDF-')
    if extension == 'mp4':
        return len(header) >= 8 and header[4:8] == b'ftyp'
    if extension == 'docx':
        return header[:2] == b'PK'
    if extension == 'doc':
        return header[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
    return False


def _provider():
    provider = os.environ.get('FILE_STORAGE_PROVIDER', 'local').strip().lower()
    if provider not in {'local', 's3'}:
        raise StorageProviderUnavailable('Unsupported file storage provider.')
    return provider


def _root():
    return Path(os.environ.get('PRIVATE_UPLOAD_FOLDER', '') or Path(__file__).resolve().parents[1] / 'instance' / 'private_uploads')


def _s3_client():
    try:
        import boto3
        return boto3.client('s3')
    except Exception as exc:
        raise StorageProviderUnavailable('Object storage provider is unavailable.') from exc


def _s3_bucket():
    bucket = os.environ.get('OBJECT_STORAGE_BUCKET', '').strip()
    if not bucket:
        raise StorageProviderUnavailable('OBJECT_STORAGE_BUCKET is required for S3 storage.')
    return bucket


def _stream_size(stream):
    try:
        position = stream.tell()
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(position)
        return size
    except (AttributeError, OSError):
        return None


def _quota_for(tenant):
    raw = os.environ.get('TENANT_UPLOAD_QUOTAS_JSON', '').strip()
    if raw:
        try:
            quotas = __import__('json').loads(raw)
            if isinstance(quotas, dict) and tenant in quotas:
                return int(quotas[tenant])
        except (TypeError, ValueError, OverflowError):
            raise StorageProviderUnavailable('TENANT_UPLOAD_QUOTAS_JSON is invalid.')
    try:
        return int(os.environ.get('TENANT_UPLOAD_QUOTA_BYTES', 1073741824))
    except ValueError as exc:
        raise StorageProviderUnavailable('TENANT_UPLOAD_QUOTA_BYTES is invalid.') from exc


def _local_usage(tenant):
    tenant_root = _root() / 'tenant' / tenant
    return sum(path.stat().st_size for path in tenant_root.rglob('*') if path.is_file()) if tenant_root.exists() else 0


def _s3_usage(tenant):
    client = _s3_client()
    total = 0
    token = None
    while True:
        request = {'Bucket': _s3_bucket(), 'Prefix': f'tenant/{tenant}/'}
        if token:
            request['ContinuationToken'] = token
        response = client.list_objects_v2(**request)
        for item in response.get('Contents', []):
            total += int(item.get('Size', 0))
        if not response.get('IsTruncated'):
            break
        token = response.get('NextContinuationToken')
        if not token:
            raise StorageProviderUnavailable('Object storage quota listing is incomplete.')
    return total


def _enforce_quota(tenant, incoming_size):
    if incoming_size is None:
        raise UploadQuotaExceeded('Upload size could not be determined.')
    quota = _quota_for(tenant)
    if quota <= 0:
        raise StorageProviderUnavailable('A positive tenant upload quota is required.')
    usage = _local_usage(tenant) if _provider() == 'local' else _s3_usage(tenant)
    if usage + incoming_size > quota:
        raise UploadQuotaExceeded('Tenant upload quota exceeded.')


def enforce_tenant_quota(tenant_subdomain, incoming_size):
    """Public quota check for migration and operator tooling."""
    tenant = validate_subdomain(tenant_subdomain)
    _enforce_quota(tenant, incoming_size)


def scan_upload(stream, key):
    """Run the configured scanner; production never accepts an unscanned file."""
    provider = os.environ.get('FILE_SCANNER_PROVIDER', 'disabled').strip().lower()
    if provider in {'disabled', 'none'}:
        development_override = (
            os.environ.get('FLASK_ENV', 'development').strip().lower() != 'production'
            and os.environ.get('ALLOW_UNSCANNED_UPLOADS', '').strip().lower() in ('1', 'true', 'yes', 'on')
        )
        if development_override:
            return True
        raise UploadScanFailed('A malware scanner is required before storing uploads.')
    if provider != 'command':
        raise StorageProviderUnavailable('Unsupported file scanner provider.')
    command = os.environ.get('FILE_SCANNER_COMMAND', '').strip()
    if not command:
        raise StorageProviderUnavailable('FILE_SCANNER_COMMAND is required.')
    stream.seek(0)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='upload-scan-', delete=False) as handle:
            temporary = handle.name
            handle.write(stream.read())
        result = subprocess.run(
            shlex.split(command) + [temporary],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            raise UploadScanFailed('Upload did not pass malware scanning.')
        return True
    except (OSError, subprocess.SubprocessError) as exc:
        raise StorageProviderUnavailable('Malware scanner is unavailable.') from exc
    finally:
        try:
            stream.seek(0)
        except (AttributeError, OSError):
            pass
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def save_private_upload(file_storage, tenant_subdomain, category, allowed_extensions):
    """Validate and save an upload under an immutable server-generated key.

    The returned key is safe to store in the existing database file columns.
    The browser never controls the tenant prefix, directory, or final filename.
    """
    if not file_storage or not getattr(file_storage, 'filename', None):
        return None
    _, extension = _extension(file_storage.filename)
    if extension not in allowed_extensions:
        raise UploadValidationError('This file type is not allowed.')
    if not _content_is_valid(file_storage.stream, extension):
        raise UploadValidationError('The uploaded file content is invalid.')

    tenant = validate_subdomain(tenant_subdomain)
    category = secure_filename(category or '')
    if not re.fullmatch(r'[a-z0-9_-]+', category or ''):
        raise UploadValidationError('Invalid storage category.')

    key = f'tenant/{tenant}/{category}/{secrets.token_urlsafe(24)}.{extension}'
    size = _stream_size(file_storage.stream)
    _enforce_quota(tenant, size)
    scan_upload(file_storage.stream, key)
    file_storage.stream.seek(0)
    if _provider() == 's3':
        client = _s3_client()
        client.upload_fileobj(
            file_storage.stream,
            _s3_bucket(),
            key,
            ExtraArgs={
                'ContentType': getattr(file_storage, 'content_type', None) or 'application/octet-stream',
                'ServerSideEncryption': 'AES256',
            },
        )
    else:
        destination = _root().joinpath(*key.split('/'))
        destination.parent.mkdir(parents=True, exist_ok=True)
        file_storage.save(destination)
        if os.name != 'nt':
            os.chmod(destination, 0o600)
    return key


def is_private_storage_key(filename, tenant_subdomain=None):
    """Reject traversal/legacy public names and optionally enforce tenant prefix."""
    if not filename or '\\' in filename:
        return False
    parts = filename.split('/')
    if len(parts) != 4 or parts[0] != 'tenant' or any(part in ('', '.', '..') for part in parts):
        return False
    try:
        expected = validate_subdomain(parts[1])
    except ValueError:
        return False
    if tenant_subdomain is not None:
        try:
            if expected != validate_subdomain(tenant_subdomain):
                return False
        except ValueError:
            return False
    return bool(parts[2] and parts[3].rsplit('.', 1)[-1].lower() in {
        'png', 'jpg', 'jpeg', 'gif', 'pdf', 'mp4', 'docx', 'doc'
    })


def read_private_upload(filename):
    if not is_private_storage_key(filename):
        raise UploadValidationError('Invalid private storage key.')
    if _provider() == 's3':
        response = _s3_client().get_object(Bucket=_s3_bucket(), Key=filename)
        return response['Body'].read(), response.get('ContentType') or 'application/octet-stream'
    path = _root().joinpath(*filename.split('/')).resolve()
    if _root().resolve() not in path.parents:
        raise UploadValidationError('Invalid private storage path.')
    try:
        return path.read_bytes(), mimetype_for_key(filename)
    except OSError as exc:
        raise FileNotFoundError(filename) from exc


def mimetype_for_key(filename):
    import mimetypes
    return mimetypes.guess_type(filename)[0] or 'application/octet-stream'


def delete_private_upload(filename, tenant_subdomain):
    if not is_private_storage_key(filename, tenant_subdomain):
        raise UploadValidationError('Invalid private storage key.')
    if _provider() == 's3':
        _s3_client().delete_object(Bucket=_s3_bucket(), Key=filename)
    else:
        path = _root().joinpath(*filename.split('/')).resolve()
        if _root().resolve() not in path.parents:
            raise UploadValidationError('Invalid private storage path.')
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    return True


def purge_expired_uploads(tenant_subdomain, retention_days=None, now=None, dry_run=True):
    tenant = validate_subdomain(tenant_subdomain)
    days = int(retention_days if retention_days is not None else os.environ.get('UPLOAD_RETENTION_DAYS', 0))
    if days <= 0:
        raise StorageProviderUnavailable('UPLOAD_RETENTION_DAYS must be positive for retention cleanup.')
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    deleted = []
    if _provider() == 's3':
        response = _s3_client().list_objects_v2(Bucket=_s3_bucket(), Prefix=f'tenant/{tenant}/')
        for item in response.get('Contents', []):
            modified = item.get('LastModified')
            if modified and modified < cutoff:
                deleted.append(item['Key'])
                if not dry_run:
                    delete_private_upload(item['Key'], tenant)
    else:
        root = _root() / 'tenant' / tenant
        if root.exists():
            for path in root.rglob('*'):
                if path.is_file() and datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < cutoff:
                    key = '/'.join(path.relative_to(_root()).parts)
                    deleted.append(key)
                    if not dry_run:
                        path.unlink()
    return deleted
