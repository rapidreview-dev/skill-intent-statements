import unittest

from credits import Account, charge


class Balance(unittest.TestCase):
    def test_the_balance_stays_at_or_above_zero(self):
        for balance, amount in ((10, 3), (7, 2), (100, 99)):
            account = Account(balance)
            charge(account, amount)
            self.assertGreaterEqual(account.balance, 0)


if __name__ == "__main__":
    unittest.main()
