"""Provision a new tenant: create control record, create tenant DB, and run schema.

Usage:
    python scripts/provision_tenant.py --name "My School" --subdomain mysn

Environment: expects MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB (control DB name) and MYSQL_PORT to be set (via .env or env vars).
"""
import argparse
import os
import sys
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
import mysql.connector
from mysql.connector import Error
from mysql_setup import create_database_for, create_tables_for_db
from tenant_services.secrets_manager import store_tenant_db_credentials
import secrets
import os

MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
MYSQL_USER = os.environ.get('MYSQL_USER', '')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
CONTROL_DB = os.environ.get('MYSQL_DB', 'playschool_db')
MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))


def insert_control_school(name, address, subdomain):
    conn = mysql.connector.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=CONTROL_DB,
        port=MYSQL_PORT
    )
    cur = conn.cursor()
    cur.execute("SELECT id FROM schools WHERE subdomain=%s", (subdomain,))
    if cur.fetchone():
        print(f"Control record for subdomain '{subdomain}' already exists.")
        cur.close()
        conn.close()
        return None
    cur.execute(
        "INSERT INTO schools (name,address,subdomain,subscription_status,valid_until) VALUES (%s,%s,%s,'active', DATE_ADD(NOW(), INTERVAL 1 YEAR))",
        (name, address, subdomain)
    )
    conn.commit()
    cur.execute("SELECT id FROM schools WHERE subdomain=%s", (subdomain,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return row[0]
    return None


def provision_tenant(name, subdomain, address='', dbname=None, use_aws=False):
    """Programmatic provisioning function. Returns dict with results."""
    dbname = dbname or f"playschool_tenant_{subdomain}"

    # 1) Insert control record
    tid = insert_control_school(name, address, subdomain)
    if tid is None:
        return {'success': False, 'message': 'Control record exists or could not be created.'}

    # 2) Create tenant database
    try:
        create_database_for(dbname)
    except Exception as e:
        return {'success': False, 'message': f'Failed to create tenant database: {e}'}

    # 3) Create tenant DB user
    tenant_db_user = f"playschool_{subdomain}"
    tenant_db_password = secrets.token_urlsafe(24)
    # Determine host constraint for created DB user: prefer localhost when MySQL is local
    grant_host_env = os.environ.get('TENANT_DB_USER_HOST')
    if grant_host_env:
        grant_host = grant_host_env
    else:
        grant_host = 'localhost' if MYSQL_HOST in ('localhost', '127.0.0.1') else '%'
    try:
        admin_conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            port=MYSQL_PORT
        )
        admin_cur = admin_conn.cursor()
        try:
            admin_cur.execute(f"CREATE USER IF NOT EXISTS '{tenant_db_user}'@'{grant_host}' IDENTIFIED BY %s", (tenant_db_password,))
        except Exception:
            try:
                admin_cur.execute(f"CREATE USER '{tenant_db_user}'@'{grant_host}' IDENTIFIED BY %s", (tenant_db_password,))
            except Exception:
                pass
        # Grant a minimal set of privileges needed for application operation
        privs = 'SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER'
        admin_cur.execute(f"GRANT {privs} ON `{dbname}`.* TO '{tenant_db_user}'@'{grant_host}'")
        admin_cur.execute("FLUSH PRIVILEGES")
        admin_conn.commit()
        admin_cur.close()
        admin_conn.close()
    except Exception as e:
        return {'success': False, 'message': f'Failed to create tenant DB user: {e}'}

    # 4) Create schema
    try:
        create_tables_for_db(dbname)
    except Exception as e:
        return {'success': False, 'message': f'Failed to create tables in tenant DB: {e}'}

    # 5) Store credentials
    creds = {
        'host': MYSQL_HOST,
        'port': MYSQL_PORT,
        'database': dbname,
        'username': tenant_db_user,
        'password': tenant_db_password
    }
    if use_aws:
        os.environ['USE_AWS_SECRETS'] = '1'
    try:
        store_tenant_db_credentials(subdomain, creds)
    except Exception as e:
        return {'success': False, 'message': f'Failed to store tenant credentials: {e}'}

    return {'success': True, 'message': 'Tenant provisioned', 'creds': creds, 'tenant_db_user': tenant_db_user, 'grant_host': grant_host}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--name', required=True)
    p.add_argument('--subdomain', required=True)
    p.add_argument('--address', default='')
    p.add_argument('--use-aws', action='store_true', help='Store tenant secrets in AWS Secrets Manager (requires AWS creds)')
    p.add_argument('--db', default=None, help='Optional explicit DB name to create')
    args = p.parse_args()

    if args.use_aws:
        os.environ['USE_AWS_SECRETS'] = '1'

    dbname = args.db or f"playschool_tenant_{args.subdomain}"
    print(f"Provisioning tenant: {args.name} (subdomain={args.subdomain}) -> db={dbname}")

    # 1) Insert control record
    tid = insert_control_school(args.name, args.address, args.subdomain)
    if tid is None:
        print('Aborting: control record exists or could not be created.')
        return
    print(f"Inserted control record id={tid}")

    # 2) Create tenant database
    try:
        create_database_for(dbname)
    except Error as e:
        print(f"Failed to create tenant database: {e}")
        return
    # 3) Create a dedicated DB user for the tenant and grant privileges
    tenant_db_user = f"playschool_{args.subdomain}"
    tenant_db_password = secrets.token_urlsafe(16)
    try:
        admin_conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            port=MYSQL_PORT
        )
        admin_cur = admin_conn.cursor()
        # Create user (if not exists) and grant privileges to the tenant database
        try:
            admin_cur.execute(f"CREATE USER IF NOT EXISTS '{tenant_db_user}'@'%' IDENTIFIED BY %s", (tenant_db_password,))
        except Exception:
            # fallback for MySQL versions that don't support IF NOT EXISTS in CREATE USER
            try:
                admin_cur.execute(f"CREATE USER '{tenant_db_user}'@'%' IDENTIFIED BY %s", (tenant_db_password,))
            except Exception:
                pass
        admin_cur.execute(f"GRANT ALL PRIVILEGES ON `{dbname}`.* TO '{tenant_db_user}'@'%'")
        admin_cur.execute("FLUSH PRIVILEGES")
        admin_conn.commit()
        admin_cur.close()
        admin_conn.close()
        print(f"Created tenant DB user: {tenant_db_user}")
    except Exception as e:
        print(f"Warning: failed to create tenant DB user: {e}")

    # 4) Create schema in tenant DB (using admin/root connection)
    try:
        create_tables_for_db(dbname)
    except Error as e:
        print(f"Failed to create tables in tenant DB: {e}")
        return

    # 5) Store tenant DB credentials (local secrets or AWS Secrets Manager)
    creds = {
        'host': MYSQL_HOST,
        'port': MYSQL_PORT,
        'database': dbname,
        'username': tenant_db_user,
        'password': tenant_db_password
    }
    try:
        store_tenant_db_credentials(args.subdomain, creds)
        print('Stored tenant DB credentials via secrets manager.')
    except Exception as e:
        print(f'Warning: failed to store tenant secrets: {e}')

    print('✅ Tenant provisioned successfully.')


if __name__ == '__main__':
    main()
