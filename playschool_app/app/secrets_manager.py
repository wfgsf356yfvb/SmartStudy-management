"""Abstracted secrets manager with local fallback and optional AWS SecretsManager support.

Usage:
- Call `store_tenant_db_credentials(subdomain, payload_dict)` to persist tenant DB creds.
- Call `get_tenant_db_credentials(subdomain)` to retrieve.

If AWS credentials are configured and `USE_AWS_SECRETS` env var is set, this will use boto3 SecretsManager.
Otherwise it writes/reads `.tenant_secrets.json` in the project root (local dev only).
"""
import os
import json

SECRETS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.tenant_secrets.json')


def _local_store(subdomain, data):
    store = {}
    if os.path.exists(SECRETS_FILE):
        try:
            with open(SECRETS_FILE, 'r', encoding='utf-8') as f:
                store = json.load(f)
        except Exception:
            store = {}
    store[subdomain] = data
    with open(SECRETS_FILE, 'w', encoding='utf-8') as f:
        json.dump(store, f, indent=2)


def _local_get(subdomain):
    if not os.path.exists(SECRETS_FILE):
        return None
    try:
        with open(SECRETS_FILE, 'r', encoding='utf-8') as f:
            store = json.load(f)
        return store.get(subdomain)
    except Exception:
        return None
def _get_sm_client():
    """Return a boto3 secretsmanager client if AWS use is enabled and boto3 is available, else None."""
    use_aws = os.environ.get('USE_AWS_SECRETS', '').lower() in ('1', 'true', 'yes')
    if not use_aws:
        return None
    try:
        import boto3
        from botocore.exceptions import ClientError  # noqa: F401
        return boto3.client('secretsmanager')
    except Exception:
        return None


def store_tenant_db_credentials(subdomain, payload):
    """Payload example: {'host':..., 'port':..., 'database':..., 'username':..., 'password':...} """
    _sm = _get_sm_client()
    if _sm:
        name = f"playschool/tenant/{subdomain}"
        try:
            _sm.create_secret(Name=name, SecretString=json.dumps(payload))
        except Exception:
            try:
                _sm.put_secret_value(SecretId=name, SecretString=json.dumps(payload))
            except Exception:
                raise
        return True
    else:
        _local_store(subdomain, payload)
        return True


def get_tenant_db_credentials(subdomain):
    _sm = _get_sm_client()
    if _sm:
        name = f"playschool/tenant/{subdomain}"
        try:
            r = _sm.get_secret_value(SecretId=name)
            return json.loads(r['SecretString'])
        except Exception:
            return None
    return _local_get(subdomain)
