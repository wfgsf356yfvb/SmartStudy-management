import os
import mysql.connector

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

    new_email = 'y0263320@gmail.com'
    try:
        cnx = mysql.connector.connect(**cfg)
    except mysql.connector.Error as err:
        print('DB connection error:', err)
        return

    cur = cnx.cursor()
    # Find any existing users with the target email
    cur.execute('SELECT id, role, email FROM users WHERE email=%s', (new_email,))
    dup = cur.fetchall()
    if dup:
        for d in dup:
            uid, role, email = d
            # If this is already a super_admin with target email, nothing to do
            if role == 'super_admin':
                print(f'super_admin id={uid} already has email {new_email}')
                continue
            # Rename duplicate to a safe placeholder to free the email
            backup_email = f'deleted_{uid}@example.invalid'
            cur.execute('UPDATE users SET email=%s WHERE id=%s', (backup_email, uid))
            print(f'Backed up existing user id={uid} email {email} -> {backup_email}')

    # Now update super_admin accounts: pick a primary and backup others
    cur.execute("SELECT id, email FROM users WHERE role='super_admin'")
    rows = cur.fetchall()
    if not rows:
        print('No super_admin accounts found.')
    else:
        # Find if any super_admin already has the target email
        primary_id = None
        for uid, email in rows:
            if email == new_email:
                primary_id = uid
                break
        # If none, choose the first as primary
        if primary_id is None:
            primary_id = rows[0][0]
            # Set primary's email to new_email later

        for uid, email in rows:
            if uid == primary_id:
                if email == new_email:
                    print(f'super_admin id={uid} already primary with {new_email}')
                else:
                    # Before setting, ensure no duplicate (should be handled above)
                    try:
                        cur.execute('UPDATE users SET email=%s WHERE id=%s', (new_email, uid))
                        print(f'Updated primary super_admin id={uid} email {email} -> {new_email}')
                    except mysql.connector.errors.IntegrityError as e:
                        print('Integrity error setting primary email:', e)
            else:
                # backup other super_admins
                backup = f'deleted_super_{uid}@example.invalid'
                cur.execute('UPDATE users SET email=%s WHERE id=%s', (backup, uid))
                print(f'Backed up other super_admin id={uid} email {email} -> {backup}')

        cnx.commit()
        print('Super_admin email normalization complete.')

    cur.close()
    cnx.close()

if __name__ == '__main__':
    main()
