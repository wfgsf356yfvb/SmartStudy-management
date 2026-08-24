"""Legacy SQLite migration helper.

This file is not part of the live Flask/MySQL runtime. It intentionally performs
schema-only changes and never creates a default school or account.
"""

import sqlite3


def main():
    conn = sqlite3.connect('playschool.db')
    try:
        cur = conn.cursor()
        cur.execute('''
        CREATE TABLE IF NOT EXISTS schools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(255) NOT NULL,
            address VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );''')
        try:
            cur.execute("ALTER TABLE users ADD COLUMN school_id INTEGER REFERENCES schools(id);")
        except sqlite3.OperationalError:
            pass
        conn.commit()
    finally:
        conn.close()


if __name__ == '__main__':
    main()
