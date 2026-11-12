"""Credits: each review costs credits, taken from the account's balance."""


class Account:
    def __init__(self, balance=0):
        self.balance = balance


def charge(account, amount):
    """Take `amount` credits from the account. Returns the new balance."""
    account.balance -= amount
    return account.balance


def bill_review(account, files):
    """Charge one review: 2 credits, and 1 more for each 10 files."""
    return charge(account, 2 + files // 10)


def refund(account, amount):
    """Give credits back, as support does after a failed review."""
    return charge(account, -amount)
