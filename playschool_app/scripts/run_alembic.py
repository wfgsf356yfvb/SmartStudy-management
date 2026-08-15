"""Run Alembic migrations against a tenant DB using stored secrets.

Usage:
  python scripts/run_alembic.py --subdomain acme --alembic_ini infra/alembic.ini

Requires: `alembic` and `sqlalchemy` packages installed in your virtualenv.
"""
import os
import argparse
import json
from tenant_services.secrets_manager import get_tenant_db_credentials

try:
    from alembic.config import Config
    from alembic import command
except Exception:
    print('Alembic not installed. Install with: pip install alembic sqlalchemy')
    raise


def build_url(creds):
    user = creds['username']
    pw = creds['password']
    host = creds['host']
    port = creds.get('port', 3306)
    db = creds['database']
    return f'mysql+pymysql://{user}:{pw}@{host}:{port}/{db}'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--subdomain', required=True)
    p.add_argument('--alembic_ini', default='alembic.ini')
    args = p.parse_args()

    creds = get_tenant_db_credentials(args.subdomain)
    if not creds:
        print('No credentials found for tenant. Provision tenant first or store creds in secrets manager.')
        return

    url = build_url(creds)
    cfg = Config(args.alembic_ini)
    cfg.set_main_option('sqlalchemy.url', url)

    print('Running alembic upgrade head against', url)
    command.upgrade(cfg, 'head')

if __name__ == '__main__':
    main()
