import sqlite3
conn = sqlite3.connect('playschool.db')
try:
    conn.execute("ALTER TABLE payments ADD COLUMN screenshot TEXT;")
    conn.commit()
    print("Successfully added screenshot column to payments table.")
except Exception as e:
    print(f"Error adding column: {e}")
conn.close()
