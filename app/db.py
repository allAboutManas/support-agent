import sqlite3

from app.config import BASE_DIR

DB_PATH = BASE_DIR / "support.db"


def get_db_connection():
    """Create a database connection with foreign-key enforcement enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create the user-scoped schema and discard legacy unowned orders."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'orders'"
        )
        if cursor.fetchone():
            columns = {
                row["name"] for row in cursor.execute("PRAGMA table_info(orders)")
            }
            if "user_id" not in columns:
                cursor.execute("DROP TABLE IF EXISTS refunds")
                cursor.execute("DROP TABLE orders")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                price REAL NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS orders_user_id_idx ON orders (user_id)"
        )

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
        conn.commit()
    finally:
        conn.close()
