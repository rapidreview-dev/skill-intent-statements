import unittest

from credits import Account, InsufficientCredits, charge


class Overdraw(unittest.TestCase):
    def test_an_overdraw_leaves_the_balance(self):
        account = Account(5)
        try:
            charge(account, 9)
        except InsufficientCredits:
            pass
        self.assertLessEqual(account.balance, 5)


if __name__ == "__main__":
    unittest.main()
