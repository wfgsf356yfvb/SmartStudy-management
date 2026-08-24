"""Secure, compensating provisioning workflow for one tenant."""

import argparse
import os
import re
import secrets
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import mysql.connector

from mysql_setup import create_database_for, create_tables_for_db
from tenant_services.middleware.tenant_resolver import validate_subdomain
from tenant_services.secrets_manager import (
    CredentialNotFound,
    delete_tenant_db_credentials,
    ensure_tenant_credential_provider_writable,
    get_tenant_db_credentials,
    store_tenant_db_credentials,
)
from scripts.audit import log as audit_log


MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
CONTROL_DB = os.environ.get('MYSQL_DB', 'playschool_db')
MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))


class ProvisioningError(RuntimeError):
    """A provisioning step failed and was compensated where possible."""


def _admin_config(database=None):
    user = os.environ.get('PROVISIONING_MYSQL_USER', '').strip()
    password = os.environ.get('PROVISIONING_MYSQL_PASSWORD', '')
    if not user or not password or user.lower() == 'root':
        raise ProvisioningError('A non-root provisioning database account is required.')
    config = {'host': MYSQL_HOST, 'user': user, 'password': password, 'port': MYSQL_PORT}
    if database:
        config['database'] = database
    return config


def _grant_config():
    user = os.environ.get('TENANT_GRANT_MYSQL_USER', '').strip()
    password = os.environ.get('TENANT_GRANT_MYSQL_PASSWORD', '')
    provisioning_user = os.environ.get('PROVISIONING_MYSQL_USER', '').strip()
    if not user or not password:
        raise ProvisioningError('A separate tenant grant database account is required.')
    if user.lower() == 'root' or user.lower() == provisioning_user.lower():
        raise ProvisioningError('The tenant grant database account must be non-root and separate.')
    return {'host': MYSQL_HOST, 'user': user, 'password': password, 'port': MYSQL_PORT}


def _identifier(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_]+', value):
        raise ProvisioningError(f'Invalid {label}.')
    return value


def _normalized_subdomain_identifier(subdomain):
    """Convert a validated hostname label into a MySQL identifier fragment."""
    if not isinstance(subdomain, str):
        raise ProvisioningError('Invalid tenant subdomain.')
    return _identifier(subdomain.replace('-', '_'), 'tenant identifier')


def tenant_database_name(subdomain):
    subdomain = validate_subdomain(subdomain)
    return _identifier(
        f'playschool_tenant_{_normalized_subdomain_identifier(subdomain)}',
        'tenant database name',
    )


def tenant_database_username(subdomain):
    subdomain = validate_subdomain(subdomain)
    return _identifier(
        f'playschool_{_normalized_subdomain_identifier(subdomain)}',
        'tenant database user',
    )


def _validated_tenant_database_name(subdomain, dbname=None):
    canonical_dbname = tenant_database_name(subdomain)
    if dbname is None:
        return canonical_dbname
    dbname = _identifier(dbname, 'tenant database name')
    if dbname != canonical_dbname:
        raise ProvisioningError('Tenant database name must match the canonical subdomain-derived name.')
    return dbname


def _account_host():
    host = os.environ.get('TENANT_DB_USER_HOST', '').strip()
    if not host:
        raise ProvisioningError('TENANT_DB_USER_HOST is required for tenant database accounts.')
    # MySQL host wildcards are allowed only for a specifically configured
    # private Docker/VPC subnet; a global wildcard is never accepted.
    private_wildcard = re.fullmatch(
        r'(?:10\.[0-9]{1,3}(?:\.[0-9]{1,3})?|'
        r'172\.(?:1[6-9]|2[0-9]|3[0-1])(?:\.[0-9]{1,3})?|'
        r'192\.168\.[0-9]{1,3})\.%',
        host,
    )
    exact_host = re.fullmatch(r'[A-Za-z0-9_.:-]+', host)
    if host == '%' or (not exact_host and not private_wildcard):
        raise ProvisioningError('Tenant database account host must be an explicit host or private subnet wildcard.')
    return host


def _account_sql(value):
    return value.replace('`', '``').replace("'", "''")


def get_control_school_by_subdomain(subdomain):
    subdomain = validate_subdomain(subdomain)
    conn = mysql.connector.connect(**_admin_config(CONTROL_DB))
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            'SELECT id, name, subdomain, subscription_status FROM schools WHERE subdomain=%s',
            (subdomain,),
        )
        return cur.fetchone()
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()


def insert_control_school(name, address, subdomain, status='provisioning'):
    subdomain = validate_subdomain(subdomain)
    conn = mysql.connector.connect(**_admin_config(CONTROL_DB))
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO schools (name,address,subdomain,subscription_status,valid_until) "
            "VALUES (%s,%s,%s,%s, DATE_ADD(NOW(), INTERVAL 1 YEAR))",
            (name, address, subdomain, status),
        )
        conn.commit()
        return cur.lastrowid
    except Exception as exc:
        conn.rollback()
        raise ProvisioningError('Control database mapping could not be created.') from exc
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()


def activate_control_school(school_id, subdomain):
    conn = mysql.connector.connect(**_admin_config(CONTROL_DB))
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE schools SET subscription_status='active' WHERE id=%s AND subdomain=%s AND subscription_status='provisioning'",
            (school_id, subdomain),
        )
        if cur.rowcount != 1:
            raise ProvisioningError('Control database mapping could not be activated.')
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()


def delete_control_school(school_id, subdomain):
    conn = mysql.connector.connect(**_admin_config(CONTROL_DB))
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM schools WHERE id=%s AND subdomain=%s AND subscription_status='provisioning'",
            (school_id, subdomain),
        )
        conn.commit()
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()


def _create_tenant_user(dbname, username, password, grant_host):
    dbname = _identifier(dbname, 'tenant database name')
    username = _identifier(username, 'tenant database user')
    host = _account_sql(grant_host)
    admin_conn = mysql.connector.connect(**_admin_config())
    grant_conn = None
    try:
        admin_cur = admin_conn.cursor()
        admin_cur.execute(
            f"CREATE USER IF NOT EXISTS '{_account_sql(username)}'@'{host}' IDENTIFIED BY %s",
            (password,),
        )
        grant_conn = mysql.connector.connect(**_grant_config())
        grant_cur = grant_conn.cursor()
        grant_cur.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE "
            f"ON `{dbname}`.* TO '{_account_sql(username)}'@'{host}'"
        )
        grant_conn.commit()
        admin_conn.commit()
    except Exception as exc:
        try:
            admin_conn.rollback()
        except Exception:
            pass
        if grant_conn is not None:
            try:
                grant_conn.rollback()
            except Exception:
                pass
        raise ProvisioningError(
            'Tenant database account could not be created.'
        ) from exc
    finally:
        try:
            admin_cur.close()
        except Exception:
            pass
        try:
            grant_cur.close()
        except Exception:
            pass
        admin_conn.close()
        if grant_conn is not None:
            grant_conn.close()


def _cleanup_database_and_user(dbname, username, grant_host):
    conn = mysql.connector.connect(**_admin_config())
    try:
        cur = conn.cursor()
        host = _account_sql(grant_host)
        cur.execute(f"DROP USER IF EXISTS '{_account_sql(username)}'@'{host}'")
        cur.execute(f"DROP DATABASE IF EXISTS `{_identifier(dbname, 'tenant database name')}`")
        conn.commit()
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()


def _safe_error(exc):
    return re.sub(r'(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*[^,; ]+', r'\1=[redacted]', str(exc))


def provision_tenant(name, subdomain, address='', dbname=None, use_aws=False):
    """Create isolated tenant resources and publish control mapping last."""
    subdomain = validate_subdomain(subdomain)
    dbname = _validated_tenant_database_name(subdomain, dbname)
    username = tenant_database_username(subdomain)
    grant_host = _account_host()
    database_created = False
    user_created = False
    secret_stored = False
    control_school_id = None

    try:
        _admin_config()
        configured_provider = os.environ.get('TENANT_CREDENTIAL_PROVIDER', '').strip().lower()
        if use_aws != (configured_provider == 'aws'):
            raise ProvisioningError('Provisioning credential-provider option does not match server configuration.')
        ensure_tenant_credential_provider_writable()
        if get_control_school_by_subdomain(subdomain):
            raise ProvisioningError('Tenant subdomain already exists.')
        try:
            get_tenant_db_credentials(subdomain)
        except CredentialNotFound:
            pass
        else:
            raise ProvisioningError('Orphaned tenant credentials already exist for this subdomain.')

        control_school_id = insert_control_school(name, address, subdomain)
        database_created = True
        create_database_for(dbname, connection_config=_admin_config())
        password = secrets.token_urlsafe(32)
        user_created = True
        _create_tenant_user(dbname, username, password, grant_host)
        create_tables_for_db(dbname, connection_config=_admin_config())
        store_tenant_db_credentials(subdomain, {
            'host': MYSQL_HOST, 'port': MYSQL_PORT, 'database': dbname,
            'username': username, 'password': password,
        })
        secret_stored = True
        activate_control_school(control_school_id, subdomain)
        return {'success': True, 'message': 'Tenant provisioned', 'tenant_id': control_school_id,
                'subdomain': subdomain, 'database': dbname, 'tenant_db_user': username,
                'grant_host': grant_host}
    except Exception as exc:
        if control_school_id:
            try:
                delete_control_school(control_school_id, subdomain)
            except Exception:
                pass
        if secret_stored:
            try:
                delete_tenant_db_credentials(subdomain)
            except Exception:
                pass
        if database_created or user_created:
            try:
                _cleanup_database_and_user(dbname, username, grant_host)
            except Exception:
                pass
        message = _safe_error(exc)
        audit_log('tenant_provisioning_failed', {
            'subdomain': subdomain, 'message': message,
            'cleanup_attempted': bool(database_created or user_created or secret_stored),
        })
        return {'success': False, 'subdomain': subdomain, 'message': message}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', required=True)
    parser.add_argument('--subdomain', required=True)
    parser.add_argument('--address', default='')
    parser.add_argument('--use-aws', action='store_true')
    parser.add_argument('--db', default=None)
    args = parser.parse_args()
    result = provision_tenant(args.name, args.subdomain, args.address, args.db, args.use_aws)
    print(result)
    if not result.get('success'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
