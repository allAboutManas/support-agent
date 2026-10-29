import sqlite3
from pathlib import Path
from app.config import BASE_DIR

DB_PATH = BASE_DIR / "support.db"


def get_db_connection():
    """Create a db connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create table and insert data"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            item_name TEXT NOT NULL,
            price REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS refunds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders (order_id)
        )
    """)


    # Seed intial Data
    cursor.execute("SELECT COUNT(*) FROM orders")
    count = cursor.fetchone()[0]

    if count == 0:

        demo_orders = [
            ("ORD-001", "iPhone 18 Pro", 180000, "Delivered"),
            ("ORD-002", "Gaming Monitor", 80000, "Damaged"),
            ("ORD-003", "Running Shoe", 1800, "Delivered"),
            ("ORD-004", "Cookware", 80000, "Damaged"),
            ("ORD-005", "Watch", 1000, "Delivered"),
            ("ORD-006", "Led Bulb", 50, "Delivered"),
            ("ORD-007", "Keyboard", 1500, "Delivered"),
            ("ORD-008", "Shirt", 800, "Damaged"),
        ]

        cursor.executemany(
            """
            INSERT OR IGNORE INTO orders (order_id, item_name, price, status)
            VALUES (?, ?, ?, ?)
            """, demo_orders
        )
        conn.commit()
        print("DB initnalized")

        
    conn.close()