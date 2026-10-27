REFUND_APPROVAL_THRESHOLD = 50.0


def requires_refund_approval(amount: float) -> bool:
    return amount > REFUND_APPROVAL_THRESHOLD