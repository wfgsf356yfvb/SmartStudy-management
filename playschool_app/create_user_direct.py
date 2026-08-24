import os
import mysql.connector
from mysql.connector import errorcode
from werkzeug.security import generate_password_hash

def read_env(path='.env'):
    env = {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'): continue
                if '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env


def main():
    if os.environ.get('FLASK_ENV', '').strip().lower() == 'production':
        raise RuntimeError('This legacy bootstrap utility is disabled in production.')
    env = read_env('.env')
    email = os.environ.get('BOOTSTRAP_ADMIN_EMAIL', '').strip()
    pw = os.environ.get('BOOTSTRAP_ADMIN_PASSWORD', '')
    if not email or not pw:
        raise RuntimeError('Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD explicitly.')
    mysql_user = env.get('MYSQL_USER', '').strip()
    if not mysql_user or mysql_user.lower() == 'root':
        raise RuntimeError('Set a non-root MYSQL_USER in the local environment.')
    cfg = {
        'host': env.get('MYSQL_HOST', 'localhost'),
        'user': mysql_user,
        'password': env.get('MYSQL_PASSWORD', ''),
        'database': env.get('MYSQL_DB', 'playschool_db'),
        'port': int(env.get('MYSQL_PORT', 3306)),
    }

    try:
        cnx = mysql.connector.connect(**cfg)
    except mysql.connector.Error as err:
        print('DB connection error:', err)
        return

    cur = cnx.cursor()
    pw_h = generate_password_hash(pw)

    # Check existing
    cur.execute('SELECT id FROM users WHERE email=%s', (email,))
    if cur.fetchone():
        print('User already exists, skipping insert')
        cur.close()
        cnx.close()
        return

    sql = "INSERT INTO users (name,email,phone,password_hash,role,school_id,is_active) VALUES (%s,%s,%s,%s,%s,%s,%s)"
    vals = ('Auto Insert', email, '9999999999', pw_h, 'super_admin', None, 1)
    cur.execute(sql, vals)
    cnx.commit()
    print('Inserted user', email)
    cur.close()
    cnx.close()

if __name__ == '__main__':
    main()
