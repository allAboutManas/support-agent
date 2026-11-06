from app.tools.orders import search_database
from app.tools.refunds import issue_refund


def tools_for_user(user_id: int):
    def search_order(order_id: str):
        """Search orders belonging to the authenticated user."""
        return search_database(order_id, user_id)

    def issue_order_refund(order_id: str, amount: float):
        """Issue a refund for an order belonging to the authenticated user."""
        return issue_refund(order_id, amount, user_id)

    search_order.__name__ = search_database.__name__
    issue_order_refund.__name__ = issue_refund.__name__
    return [search_order, issue_order_refund]