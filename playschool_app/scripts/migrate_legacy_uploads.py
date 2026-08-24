"""Safe, operator-driven migration primitives for legacy public uploads.

The caller supplies a server-side query function and update callback so browser
input can never select an owner. A manifest supports a compensating rollback.
"""

import hashlib
import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

from tenant_services.file_storage import enforce_tenant_quota, is_private_storage_key, scan_upload
from tenant_services.middleware.tenant_resolver import validate_subdomain


OWNER_QUERIES = (
    ('users', 'profile_pic'),
    ('homework', 'file_path'),
    ('submissions', 'file_path'),
    ('payments', 'screenshot'),
    ('student_fee_payments', 'receipt_file'),
)


def find_legacy_owners(filename, query_fn):
    """Return server-side owners; migration requires exactly one owner."""
    owners = []
    for table, column in OWNER_QUERIES:
        rows = query_fn(f'SELECT id FROM {table} WHERE {column}=%s', (filename,)) or []
        for row in rows:
            owners.append({'table': table, 'column': column, 'id': row['id'] if isinstance(row, dict) else row[0]})
    return owners


def migrate_legacy_file(filename, tenant_subdomain, legacy_root, private_root, query_fn, update_fn, manifest_path):
    tenant = validate_subdomain(tenant_subdomain)
    manifest_file = Path(manifest_path).resolve()
    if manifest_file.exists():
        try:
            existing = json.loads(manifest_file.read_text(encoding='utf-8'))
            existing_key = existing['key']
            existing_target = (Path(private_root).resolve() / existing_key).resolve()
            if (existing.get('tenant') == tenant and existing.get('source') == filename
                    and is_private_storage_key(existing_key, tenant)
                    and existing_target.is_file()
                    and hashlib.sha256(existing_target.read_bytes()).hexdigest() == existing.get('sha256')):
                return existing
        except (OSError, KeyError, TypeError, ValueError):
            pass
        raise ValueError('A previous migration manifest exists and requires operator review.')
    if not filename or Path(filename).name != filename:
        raise ValueError('Legacy filename must be a basename.')
    owners = find_legacy_owners(filename, query_fn)
    if len(owners) != 1:
        raise ValueError('Legacy file must have exactly one validated owner.')
    source = (Path(legacy_root).resolve() / filename).resolve()
    if Path(legacy_root).resolve() not in source.parents or not source.is_file():
        raise FileNotFoundError(filename)
    extension = source.suffix.lower().lstrip('.')
    key = f'tenant/{tenant}/legacy/{uuid4().hex}.{extension}'
    if not is_private_storage_key(key, tenant):
        raise ValueError('Generated private storage key is invalid.')
    with open(source, 'rb') as handle:
        enforce_tenant_quota(tenant, source.stat().st_size)
        scan_upload(handle, key)
    destination = (Path(private_root).resolve() / key).resolve()
    if Path(private_root).resolve() not in destination.parents:
        raise ValueError('Migration destination is unsafe.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    if os.name != 'nt':
        os.chmod(destination, 0o600)
    owner = owners[0]
    manifest = {'tenant': tenant, 'source': filename, 'key': key, 'owner': owner,
                'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}
    try:
        update_fn(owner['table'], owner['column'], owner['id'], key)
        manifest_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = manifest_file.with_name(f'.{manifest_file.name}.tmp')
        temporary.write_text(json.dumps(manifest, sort_keys=True), encoding='utf-8')
        os.replace(temporary, manifest_file)
    except Exception:
        try:
            update_fn(owner['table'], owner['column'], owner['id'], filename)
        finally:
            destination.unlink(missing_ok=True)
        raise
    return manifest


def rollback_legacy_migration(manifest_path, private_root, update_fn, restore_source=False, legacy_root=None):
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    key = manifest['key']
    tenant = validate_subdomain(manifest['tenant'])
    if not is_private_storage_key(key, tenant):
        raise ValueError('Migration manifest contains an unsafe key.')
    target = (Path(private_root).resolve() / key).resolve()
    if Path(private_root).resolve() not in target.parents:
        raise ValueError('Migration rollback path is unsafe.')
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != manifest['sha256']:
        raise ValueError('Migrated file checksum changed; refusing rollback.')
    update_fn(manifest['owner']['table'], manifest['owner']['column'], manifest['owner']['id'], manifest['source'])
    if restore_source and legacy_root:
        source = (Path(legacy_root).resolve() / manifest['source']).resolve()
        if Path(legacy_root).resolve() not in source.parents:
            raise ValueError('Legacy rollback path is unsafe.')
        source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, source)
    if target.exists():
        target.unlink()
    return manifest
