def issue_refund(order_id: str, amount: float):
    """Return a mock refund confirmation."""
    return f"Success: Your refund of amount ${amount} is issued for {order_id}."