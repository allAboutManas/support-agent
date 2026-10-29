import sqlite3

from app.db import get_db_connection


def issue_refund(order_id: str, amount: float):
    """Record a refund and return its confirmation."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM orders WHERE order_id = ?", (order_id,))
        order = cursor.fetchone()

        if not order:
            return f"Error: Order {order_id} does not exist"

        cursor.execute(
            "INSERT INTO refunds (order_id, amount, status) VALUES (?, ?, ?)",
            (order_id, amount, "refunded"),
        )
        conn.commit()
        return f"Success: Your refund of amount ${amount} is issued for {order_id}."
    except sqlite3.Error as error:
        if conn is not None:
            conn.rollback()
        return f"Error: Unable to issue refund for {order_id}: {error}"
    finally:
        if conn is not None:
            conn.close()
