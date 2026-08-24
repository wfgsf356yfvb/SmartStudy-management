"""Explicit tenant credential providers for production and development."""

import json
import os
import stat
import tempfile

from tenant_services.middleware.tenant_resolver import validate_subdomain


class CredentialProviderUnavailable(RuntimeError):
    """The configured provider cannot be used safely."""


class CredentialNotFound(CredentialProviderUnavailable):
    """The provider is available but has no record for this tenant."""


def _provider():
    return os.environ.get('TENANT_CREDENTIAL_PROVIDER', '').strip().lower()


def _is_production():
    return os.environ.get('FLASK_ENV', 'development').strip().lower() == 'production'


def _path():
    return os.environ.get('TENANT_DB_CREDENTIALS_FILE', '').strip()


def _local_file_enabled():
    return (not _is_production() and _provider() == 'local_file'
            and os.environ.get('ALLOW_LOCAL_TENANT_CREDENTIALS', '').strip().lower()
            in ('1', 'true', 'yes', 'on') and bool(_path()))


def _protected_file_enabled():
    return _provider() == 'protected_file' and bool(_path()) and not _path().endswith('.tenant_secrets.json')


def _assert_protected_file():
    if not _protected_file_enabled():
        raise CredentialProviderUnavailable('Protected local credential storage is not explicitly configured.')
    if os.path.exists(_path()) and os.name != 'nt':
        if stat.S_IMODE(os.stat(_path()).st_mode) & 0o077:
            raise CredentialProviderUnavailable('Protected credential file permissions are too broad.')


def _read_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            records = json.load(handle)
    except FileNotFoundError as exc:
        raise CredentialNotFound('Tenant credentials are not configured.') from exc
    except (OSError, ValueError) as exc:
        raise CredentialProviderUnavailable('Tenant credential provider is unavailable.') from exc
    if not isinstance(records, dict):
        raise CredentialProviderUnavailable('Tenant credential file is invalid.')
    return records


def _get_sm_client():
    try:
        import boto3
        return boto3.client('secretsmanager')
    except Exception as exc:
        raise CredentialProviderUnavailable('AWS tenant credential provider is unavailable.') from exc


def _secret_name(subdomain):
    return f'playschool/tenant/{validate_subdomain(subdomain)}'


def ensure_tenant_credential_provider_writable():
    provider = _provider()
    if provider == 'environment':
        raise CredentialProviderUnavailable('The environment credential provider is read-only.')
    if provider == 'aws':
        _get_sm_client()
        return True
    if provider == 'protected_file':
        _assert_protected_file()
        return True
    if _local_file_enabled():
        return True
    raise CredentialProviderUnavailable('No writable tenant credential provider is explicitly configured.')


def _write_records(path, records):
    parent = os.path.dirname(os.path.abspath(path)) or os.getcwd()
    os.makedirs(parent, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.tenant-credentials-', dir=parent, text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(records, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != 'nt':
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except OSError as exc:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise CredentialProviderUnavailable('Tenant credential provider could not write credentials.') from exc


def store_tenant_db_credentials(subdomain, payload):
    subdomain = validate_subdomain(subdomain)
    provider = _provider()
    if provider == 'environment':
        raise CredentialProviderUnavailable('The environment credential provider is read-only.')
    if provider == 'aws':
        client = _get_sm_client()
        name = _secret_name(subdomain)
        try:
            client.create_secret(Name=name, SecretString=json.dumps(payload))
        except Exception:
            try:
                client.put_secret_value(SecretId=name, SecretString=json.dumps(payload))
            except Exception as exc:
                raise CredentialProviderUnavailable('AWS tenant credential provider could not store credentials.') from exc
        return True
    if provider == 'protected_file':
        _assert_protected_file()
    elif not _local_file_enabled():
        raise CredentialProviderUnavailable('No writable tenant credential provider is explicitly configured.')
    path = _path()
    records = {} if not os.path.exists(path) else _read_file(path)
    records[subdomain] = dict(payload)
    _write_records(path, records)
    return True


def delete_tenant_db_credentials(subdomain):
    subdomain = validate_subdomain(subdomain)
    provider = _provider()
    if provider == 'aws':
        try:
            _get_sm_client().delete_secret(SecretId=_secret_name(subdomain), ForceDeleteWithoutRecovery=True)
        except Exception:
            pass
        return
    if provider == 'protected_file':
        _assert_protected_file()
    elif not _local_file_enabled():
        raise CredentialProviderUnavailable('No credential provider is configured.')
    path = _path()
    if not os.path.exists(path):
        return
    records = _read_file(path)
    if subdomain in records:
        del records[subdomain]
        _write_records(path, records)


def get_tenant_db_credentials(subdomain):
    subdomain = validate_subdomain(subdomain)
    provider = _provider()
    if provider == 'environment':
        raw = os.environ.get('TENANT_DB_CREDENTIALS_JSON', '')
        if not raw:
            raise CredentialProviderUnavailable('TENANT_DB_CREDENTIALS_JSON is not configured.')
        try:
            records = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise CredentialProviderUnavailable('TENANT_DB_CREDENTIALS_JSON is invalid.') from exc
        if not isinstance(records, dict):
            raise CredentialProviderUnavailable('TENANT_DB_CREDENTIALS_JSON must contain an object.')
        credentials = records.get(subdomain)
        if not isinstance(credentials, dict):
            raise CredentialNotFound('Tenant credentials are not configured.')
        return dict(credentials)
    if provider == 'aws':
        try:
            credentials = json.loads(_get_sm_client().get_secret_value(SecretId=_secret_name(subdomain))['SecretString'])
        except Exception as exc:
            raise CredentialProviderUnavailable('AWS tenant credential provider could not retrieve credentials.') from exc
        if not isinstance(credentials, dict):
            raise CredentialProviderUnavailable('AWS tenant credential payload is invalid.')
        return credentials
    if provider == 'protected_file':
        _assert_protected_file()
    elif not _local_file_enabled():
        raise CredentialProviderUnavailable('No tenant credential provider is explicitly configured.')
    credentials = _read_file(_path()).get(subdomain)
    if not isinstance(credentials, dict):
        raise CredentialNotFound('Tenant credentials are not configured.')
    return dict(credentials)
