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
    env = read_env('.env')
    cfg = {
        'host': env.get('MYSQL_HOST', 'localhost'),
        'user': env.get('MYSQL_USER', 'root'),
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
    email = 'y0263320@gmail.com'
    pw = 'Testpass123'
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
