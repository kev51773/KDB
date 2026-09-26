import sqlite3
from pathlib import Path

DB_PATH = Path("sample_qa.db")

def generate_sample_db():
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Users Table
    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT DEFAULT 'tester',
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.executemany("""
        INSERT INTO users (username, email, role, status) VALUES (?, ?, ?, ?)
    """, [
        ("alice_qa", "alice@qa-team.com", "lead_qa", "active"),
        ("bob_dev", "bob@dev-team.com", "developer", "active"),
        ("charlie_qa", "charlie@qa-team.com", "tester", "inactive"),
        ("diana_mgr", "diana@company.com", "admin", "active")
    ])

    # Products Table
    cursor.execute("""
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            price REAL,
            stock_quantity INTEGER
        )
    """)

    cursor.executemany("""
        INSERT INTO products (name, category, price, stock_quantity) VALUES (?, ?, ?, ?)
    """, [
        ("Wireless Ergonomic Mouse", "Electronics", 29.99, 150),
        ("Mechanical Keyboard RGB", "Electronics", 89.50, 45),
        ("4K Monitor 27-inch", "Electronics", 349.00, 12),
        ("Standing Desk Mat", "Office Equipment", 45.00, 80),
        ("Coffee Mug Stainless", "Kitchen", 15.99, 200)
    ])

    # Orders Table
    cursor.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            total_amount REAL,
            payment_status TEXT,
            order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.executemany("""
        INSERT INTO orders (user_id, total_amount, payment_status) VALUES (?, ?, ?)
    """, [
        (1, 119.49, "completed"),
        (2, 349.00, "pending"),
        (1, 45.00, "completed"),
        (3, 15.99, "failed")
    ])

    # QA Test Runs Table
    cursor.execute("""
        CREATE TABLE qa_test_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_suite TEXT NOT NULL,
            passed INTEGER,
            failed INTEGER,
            skipped INTEGER,
            execution_time_sec REAL,
            environment TEXT DEFAULT 'staging'
        )
    """)

    cursor.executemany("""
        INSERT INTO qa_test_runs (test_suite, passed, failed, skipped, execution_time_sec, environment) VALUES (?, ?, ?, ?, ?, ?)
    """, [
        ("Authentication Suite", 24, 0, 1, 12.4, "staging"),
        ("Checkout & Payments", 18, 2, 0, 45.1, "staging"),
        ("User Profile API", 30, 0, 0, 8.2, "dev"),
        ("Database Migration Checks", 5, 0, 0, 3.5, "staging")
    ])

    conn.commit()
    conn.close()
    print(f"Sample QA SQLite database created at: {DB_PATH.resolve()}")

if __name__ == "__main__":
    generate_sample_db()
