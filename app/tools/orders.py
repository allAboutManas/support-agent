from app.db import get_db_connection

def search_database(order_id: str):
    """Look up an order in the demo database."""
    order_id = order_id.strip()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT order_id, item_name, price, status FROM orders WHERE order_id = ?", (order_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return f"Order with id '{order_id}' was not found"

    # Return a dictionary for agent
    return {
        "order_id": row["order_id"],
        "item": row["item_name"],
        "price": row["price"],
        "status": row["status"]
    }