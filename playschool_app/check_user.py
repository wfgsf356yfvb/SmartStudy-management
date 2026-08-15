import os
import mysql.connector
from mysql.connector import errorcode

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

    cur = cnx.cursor(dictionary=True)
    email = 'y0263320@gmail.com'
    cur.execute('SELECT * FROM users WHERE email=%s', (email,))
    row = cur.fetchone()
    if not row:
        print('No user found with email', email)
    else:
        for k, v in row.items():
            print(f"{k}: {v}")

    cur.close()
    cnx.close()

if __name__ == '__main__':
    main()
