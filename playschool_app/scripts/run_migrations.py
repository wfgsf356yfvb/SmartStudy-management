"""Simple SQL migration runner for tenant databases.

Usage:
  python scripts/run_migrations.py --subdomain acme --migrations migrations/

The script connects to the tenant DB using env vars (MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_PORT)
and database name `playschool_tenant_{subdomain}` unless --db is provided.
It creates a `schema_migrations` table in the tenant DB to track applied migration filenames.
"""
import os
import argparse
import mysql.connector
from mysql.connector import Error

MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))


def get_conn(db_name):
    return mysql.connector.connect(host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD, database=db_name, port=MYSQL_PORT)


def ensure_migrations_table(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename VARCHAR(255) PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    conn.commit()
    cur.close()


def already_applied(conn, filename):
    cur = conn.cursor()
    cur.execute("SELECT filename FROM schema_migrations WHERE filename=%s", (filename,))
    res = cur.fetchone()
    cur.close()
    return bool(res)


def mark_applied(conn, filename):
    cur = conn.cursor()
    cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (filename,))
    conn.commit()
    cur.close()


def run_migration_file(conn, path):
    with open(path, 'r', encoding='utf-8') as f:
        sql = f.read()
    cur = conn.cursor()
    for stmt in [s.strip() for s in sql.split(';') if s.strip()]:
        cur.execute(stmt)
    conn.commit()
    cur.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--subdomain', required=True)
    p.add_argument('--migrations', default='migrations')
    p.add_argument('--db', default=None)
    args = p.parse_args()

    db_name = args.db or f"playschool_tenant_{args.subdomain}"
    print(f"Connecting to tenant DB: {db_name}")
    try:
        conn = get_conn(db_name)
    except Error as e:
        print(f"Failed to connect to DB {db_name}: {e}")
        return

    ensure_migrations_table(conn)

    files = sorted([f for f in os.listdir(args.migrations) if f.endswith('.sql')])
    if not files:
        print("No migration files found in", args.migrations)
        return

    for fn in files:
        if already_applied(conn, fn):
            print(f"Skipping already applied: {fn}")
            continue
        path = os.path.join(args.migrations, fn)
        print(f"Applying {fn}...")
        try:
            run_migration_file(conn, path)
            mark_applied(conn, fn)
            print(f"Applied {fn}")
        except Exception as e:
            print(f"Failed applying {fn}: {e}")
            break

    conn.close()

if __name__ == '__main__':
    main()
