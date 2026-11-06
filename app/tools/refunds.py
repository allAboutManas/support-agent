import math
import sqlite3

from app.db import get_db_connection


def issue_refund(order_id: str, amount: float, user_id: int):
    """Record a refund for an order belonging to the authenticated user."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT price FROM orders WHERE order_id = ? AND user_id = ?",
            (order_id, user_id),
        )
        order = cursor.fetchone()

        if not order:
            return f"Error: Order {order_id} does not exist"
        if not math.isfinite(amount) or amount < 0 or amount > order["price"]:
            return f"Error: Refund amount must be between $0 and ${order['price']}"

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
