import sqlite3

def initialize_database():
    conn = sqlite3.connect("db.db")
    with open("db.sql", "r") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    print("✅ Database initialized.")

if __name__ == "__main__":
    initialize_database()
