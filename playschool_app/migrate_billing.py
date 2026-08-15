import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = 'playschool.db'

def run_migration():
    print(f"Connecting to DB at: {os.path.abspath(DB_PATH)}")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # 1. Alter schools table
        c.execute("ALTER TABLE schools ADD COLUMN subscription_status TEXT DEFAULT 'active';")
        print("Column subscription_status added.")
    except sqlite3.OperationalError as e:
        print(f"Notice: {e}")

    try:
        c.execute("ALTER TABLE schools ADD COLUMN valid_until DATE;")
        print("Column valid_until added.")
        
        # Set existing default schools to be valid for another year.
        future_date = (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')
        c.execute("UPDATE schools SET valid_until = ?", (future_date,))
        print(f"Updated existing schools expiry to {future_date}")
    except sqlite3.OperationalError as e:
        print(f"Notice: {e}")

    # 2. Create Payments table
    c.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending',
            months INTEGER DEFAULT 12,
            notes TEXT,
            FOREIGN KEY (school_id) REFERENCES schools (id)
        )
    ''')
    print("Payments table successfully initialized.")
    
    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == '__main__':
    run_migration()
