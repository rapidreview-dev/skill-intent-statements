import unittest

from app import review
from credits import Account, bill_review, charge, refund


class Credits(unittest.TestCase):
    def test_a_charge_is_taken_from_the_balance(self):
        account = Account(10)
        self.assertEqual(charge(account, 3), 7)
        self.assertEqual(account.balance, 7)

    def test_a_review_costs_two_credits_and_one_more_for_each_ten_files(self):
        account = Account(10)
        bill_review(account, 25)
        self.assertEqual(account.balance, 6)

    def test_a_refund_gives_credits_back(self):
        account = Account(1)
        refund(account, 4)
        self.assertEqual(account.balance, 5)

    def test_a_billed_review_runs(self):
        self.assertEqual(review(Account(10), 3), "reviewed 3 files")


if __name__ == "__main__":
    unittest.main()
