# Intent: Refuse a charge that would overdraw

> Credits must never go negative. A charge that would overdraw is refused and
> leaves the balance as it was. The caller has to be told, so that a review
> nobody paid for does not run.

- tests: tests/

## S1 A charge within the balance is taken
- kind: keeps
- state: checked
- given: a balance b and an amount a with 0 ≤ a ≤ b
- then: the new balance is b − a
- source: existing: tests/test_credits.py:8
- check: `python3 -m unittest tests.test_credits.Credits.test_a_charge_is_taken_from_the_balance`

## S2 A charge above the balance is refused
- kind: changes
- state: checked
- given: a balance b ≥ 0 and an amount a > b
- then: `charge` raises `InsufficientCredits`, and the balance is still b
- source: request: "A charge that would overdraw is refused and leaves the balance as it was"
- check: `python3 -m unittest tests.test_overdraw.Overdraw.test_an_overdraw_leaves_the_balance`

## S3 The balance is never negative after a charge
- kind: changes
- state: checked
- given: any account with a balance ≥ 0, and any charge
- then: the balance afterwards is ≥ 0
- source: request: "Credits must never go negative"
- check: `python3 -m unittest tests.test_balance.Balance.test_the_balance_stays_at_or_above_zero`

## S4 Amounts are never negative
- kind: assumes
- state: open
- given: every caller of `charge`
- then: `amount` is ≥ 0
- source: inferred: `bill_review` computes 2 + files // 10, which is positive
- because: no caller passes anything else, so nothing checks it.
