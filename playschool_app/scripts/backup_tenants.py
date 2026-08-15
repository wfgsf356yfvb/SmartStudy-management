"""Backup tenant databases using mysqldump and optionally upload to S3.

Usage:
  python scripts/backup_tenants.py --outdir backups/ --s3-bucket my-bucket

Requires MYSQL_ROOT credentials via env (MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_PORT).
If USE_AWS is set and bucket provided, upload each dump to S3 using boto3.
"""
import os
import argparse
import subprocess
from datetime import datetime
from tenant_services.secrets_manager import get_tenant_db_credentials


def dump_database(creds, outpath):
    user = os.environ.get('MYSQL_USER')
    pw = os.environ.get('MYSQL_PASSWORD')
    host = creds.get('host')
    port = creds.get('port', 3306)
    db = creds.get('database')
    # Use mysqldump; requires mysqldump available on PATH
    cmd = [
        'mysqldump',
        f'--host={host}',
        f'--port={port}',
        f'--user={user}',
        f'--password={pw}',
        '--single-transaction',
        '--quick',
        db
    ]
    with open(outpath, 'wb') as f:
        subprocess.check_call(cmd, stdout=f)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--outdir', default='backups')
    p.add_argument('--s3-bucket', default=None)
    args = p.parse_args()

    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)

    # Assume secrets file or AWS secrets contain tenant entries
    # Read keys from tenant_services.secrets_manager local store
    # We don't know which tenants exist; attempt to read .tenant_secrets.json
    secrets_file = os.path.join(os.path.dirname(__file__), '..', '.tenant_secrets.json')
    if not os.path.exists(secrets_file):
        print('No local tenant secrets found; ensure secrets manager or specify tenants manually.')
        return

    import json
    with open(secrets_file, 'r', encoding='utf-8') as f:
        store = json.load(f)

    for subdomain, creds in store.items():
        name = f"{subdomain}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.sql"
        outpath = os.path.join(outdir, name)
        try:
            print('Dumping', subdomain)
            dump_database(creds, outpath)
            print('Dumped to', outpath)
            if args.s3_bucket:
                try:
                    from tenant_services.s3_storage import upload_file
                    key = f"backups/{name}"
                    upload_file(args.s3_bucket, key, outpath)
                    print('Uploaded to s3://%s/%s' % (args.s3_bucket, key))
                except Exception as e:
                    print('S3 upload failed:', e)
        except Exception as e:
            print('Failed to dump', subdomain, e)


if __name__ == '__main__':
    main()
