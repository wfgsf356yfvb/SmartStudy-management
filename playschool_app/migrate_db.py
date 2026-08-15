import sqlite3
import os

DB = 'playschool.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()

print("--- Starting Manual DB Migration ---")
try:
    cur.execute('''
    CREATE TABLE IF NOT EXISTS schools (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(255) NOT NULL,
        address VARCHAR(255),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );''')
    print("Created schools table.")
except Exception as e:
    print(f"Schools table error: {e}")

try:
    cur.execute("ALTER TABLE users ADD COLUMN school_id INTEGER REFERENCES schools(id);")
    print("Added school_id column to users.")
except Exception as e:
    print(f"school_id column already exists or failed: {e}")

try:
    cur.execute("INSERT OR IGNORE INTO schools (id, name, address) VALUES (1, 'Default School', 'Main Campus')")
    cur.execute("UPDATE users SET school_id=1 WHERE school_id IS NULL AND role != 'super_admin'")
    print("Seeded Default School and migrated users.")
    
    # Ensure Super Admin exists with correct hash
    from werkzeug.security import generate_password_hash
    hashed_pw = generate_password_hash("superadmin123")
    cur.execute("SELECT id FROM users WHERE email='superadmin@playschool.com'")
    if not cur.fetchone():
        cur.execute("INSERT INTO users (name, email, phone, password_hash, role, school_id) VALUES (?,?,?,?,?,NULL)", 
                    ('Super Admin', 'superadmin@playschool.com', '0000000000', hashed_pw, 'super_admin'))
        print("Super Admin seeded with superadmin123")
    
except Exception as e:
    print(f"Seeding/SuperAdmin failed: {e}")

conn.commit()
conn.close()
print("--- Done ---")
