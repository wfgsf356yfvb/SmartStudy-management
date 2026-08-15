import sqlite3

conn = sqlite3.connect(r'c:\Users\fardi\Downloads\playschool_app\playschool_app\playschool.db')
cursor = conn.cursor()

# Show all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [t[0] for t in cursor.fetchall()]
print("Tables:", tables)
print()

# Show columns for each table
for table in tables:
    try:
        cursor.execute(f"SELECT * FROM {table} LIMIT 1")
        cols = [desc[0] for desc in cursor.description]
        print(f"Table [{table}] columns: {cols}")
    except Exception as e:
        print(f"Error reading {table}: {e}")

print()
print("=" * 60)
print("USERS / LOGIN IDs")
print("=" * 60)

# Try common user table names and login-related columns
user_tables = [t for t in tables if any(kw in t.lower() for kw in ['user', 'login', 'account', 'admin', 'teacher', 'student', 'parent'])]
print("Likely user tables:", user_tables)
print()

for table in user_tables:
    try:
        cursor.execute(f"SELECT * FROM {table}")
        rows = cursor.fetchall()
        cols = [desc[0] for desc in cursor.description]
        print(f"\n--- Table: {table} ({len(rows)} rows) ---")
        print("Columns:", cols)
        for row in rows:
            print(dict(zip(cols, row)))
    except Exception as e:
        print(f"Error: {e}")

conn.close()
