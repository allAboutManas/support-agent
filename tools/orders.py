def search_database(order_id: str):
    """Look up an order in the demo database."""
    database = {
        "ORD-001": {"item": "Iphone 18 pro", "price": 180000, "status": "Delievered"},
        "ORD-002": {"item": "Gaming Monitor", "price": 80000, "status": "Damaged"},
    }
    return database.get(order_id, "Order not found")