# The forms a check can take

A check is a command that exits 0 only when its statement holds. Below are the
forms, strongest first, with what each can and cannot show. Use the project's
own language, runner and libraries.

## Contents

- [A type](#a-type)
- [A property over generated inputs](#a-property-over-generated-inputs)
- [A comparison with the old code](#a-comparison-with-the-old-code)
- [An example](#an-example)
- [A command over the code](#a-command-over-the-code)
- [An assertion in the code](#an-assertion-in-the-code)
- [A proof](#a-proof)
- [Where code gives no answer](#where-code-gives-no-answer)

## A type

A type holds for every input and costs nothing to run. Use one where the bad
state can be made impossible to write down.

| Statement | As a type |
|---|---|
| Every case is handled | TypeScript: `default: { const rest: never = value; throw … }`. Python: `assert_never(value)` under mypy or pyright. Rust and Swift: `match` and `switch` already refuse a missing case |
| The list is never empty | TypeScript: `[T, ...T[]]`. Rust: a struct with a first item and the rest |
| The value was validated | A distinct type that only the validator returns: a branded type, `NewType`, a struct with a private field |
| The index is in range | TypeScript: `noUncheckedIndexedAccess`, so the lookup's type includes `undefined` |
| It is never null | A non-optional type, with the compiler's strict null checks on |

**The check** is the type checker, over a line that must not compile:

```ts
// tests/types.test-d.ts: `tsc --noEmit` passes only while this line is an error
// @ts-expect-error a status the switch does not handle
const bad: Status = "archived";
```

In Python, `# type: ignore[arg-type]` on that line does the same under
`mypy --warn-unused-ignores`.

## A property over generated inputs

This is the direct counterpart of a statement in a proof language: for every
input in `given`, `then` holds. A library generates inputs, and shrinks one
that breaks the property to the smallest that still does.

```python
# Hypothesis
from hypothesis import given, strategies as st

@given(balance=st.integers(min_value=0), over=st.integers(min_value=1))
def test_refuses_an_overdraw(balance, over):
    result = charge(balance, balance + over)      # every amount above the balance
    assert result.refused and result.balance == balance
```

```ts
// fast-check
import fc from "fast-check";

test("refuses an overdraw", () => {
  fc.assert(fc.property(fc.nat(), fc.integer({ min: 1 }), (balance, over) => {
    const result = charge(balance, balance + over);
    return result.refused && result.balance === balance;
  }));
});
```

```go
// testing/quick, in the standard library
func TestRefusesAnOverdraw(t *testing.T) {
    holds := func(balance, over uint16) bool {
        result := Charge(uint32(balance), uint32(balance)+uint32(over)+1)
        return result.Refused && result.Balance == uint32(balance)
    }
    if err := quick.Check(holds, nil); err != nil {
        t.Error(err)
    }
}
```

**Without a library,** a loop over the boundary values and seeded random
inputs is a property too. Seed the generator, so a failure repeats.

```python
import random

def test_refuses_an_overdraw():
    rng = random.Random(0)
    balances = [0, 1, 2**31 - 1] + [rng.randrange(10**9) for _ in range(500)]
    for balance in balances:
        for over in (1, 2, rng.randrange(1, 10**9)):
            result = charge(balance, balance + over)
            assert result.refused and result.balance == balance, (balance, over)
```

**What to assert when no expected value is at hand:**

| Pattern | Shape |
|---|---|
| Invariant | The result always satisfies P: the balance is never negative |
| Both directions | Refused exactly when the amount exceeds the balance. Test the accepted side as well as the refused one, or a function that refuses everything passes |
| Round trip | `decode(encode(x)) == x` |
| Idempotence | `f(f(x)) == f(x)` |
| Oracle | The same result as a slower, plainer or older implementation |
| Changed input, known change | Adding an item to the cart never lowers the total |

**Make the generator cover all of `given`.** A generator narrower than `given`
checks a narrower statement than the one written. Say so in the statement, or
widen it.

**Fail on what the old code does, not on a missing name.** A test file that
imports a name the change adds cannot load without the change, so every test
in it fails for that reason alone. Import the module and look the name up
where it is used:

```python
import credits

def refused(call, *arguments):
    try:
        call(*arguments)
    except credits.InsufficientCredits:   # looked up only when something is raised
        return True
    return False
```

Without the change nothing is raised, and the test fails because the charge
was taken.

## A comparison with the old code

For a `keeps` statement, the old code is the specification. Run old and new on
the same inputs and compare.

- **The old function as an oracle:** copy the old body into the test file
  under a name such as `old_slugify`, and assert `slugify(x) == old_slugify(x)`
  over generated inputs. Take the copy from git (`git show main:text.py`), not
  from memory, so that it is the old code. Delete it once the change has
  settled.
- **Recorded results:** run the base version over a list of inputs once,
  store the results as a fixture, and assert the new code gives the same.
- **Show that the comparison can fail.** It passes with and without the change
  by design. Swap in the rewrite a tired author would make (`[a-z0-9]+` for
  `\w+`) and see it fail, and assert how many inputs were compared, so a
  generator that yields nothing does not pass.

With `--base` such a check passes without the change and with it, which is
what `keeps` asks. A difference is either a case the new code misses or a
behaviour that was meant to change. Which of the two it is, the run cannot
say: if the request states the new behaviour, write a `changes` statement for
it and narrow the `keeps` one. Otherwise the new code is wrong.

## An example

One input and the result expected. It is the weakest form, and the right one
when a single input matters: the one from the bug report, or a boundary the
request names.

```python
def test_a_charge_of_the_whole_balance_is_taken():
    assert charge(5, 5).balance == 0
```

A bug fix has at least this: the reported input, failing before the fix and
passing after it.

## A command over the code

Some of what a request asks is about the code, not its behaviour: "use a
regular expression", "no new dependency", "nothing calls the old function any
more". Where a command can tell, that is the check:

```
grep -q "^import re" text.py && ! grep -q "for ch in" text.py
```

Where only a reader can tell ("easier to read"), write no statement, and say
in the report that nothing checks it.

## An assertion in the code

A postcondition or invariant written into the code itself (`assert`, an
`invariant(…)` helper) holds on every run that reaches it, in production as in
tests. It counts as a check only together with a test that reaches it. Use it
for what must never happen whatever the caller does.

## A proof

Use a prover (Lean, Dafny, Verus, TLA+, Alloy) only where the project already
has one, or the user asks.

- **Models prove little.** The best model on the VERINA benchmark wrote
  correct Lean code for 72.6% of the tasks and a proof for 4.9% (Ye et al.,
  2025). Dafny goes better: 82% against Lean's 27% on the vericoding
  benchmark (Bursuc et al., 2025).
- **Even with a proved model, most bugs come from running code.** The Cedar
  team found 4 bugs while proving and 21 by random and property-based testing
  against the model (Disselkoen et al., 2024).
- **A stated theorem is still worth having.** One without a proof is `open`,
  as `sorry` marks it in Lean. Never close it with an axiom or an assumption
  that restates it.
- **A proof the prover accepts** is `checked`, and the check is the prover's
  command.

## Where code gives no answer

Proof languages refuse code that may give no answer. Elsewhere these are the
places to walk for each function added or changed. The last two rows are
beyond what a proof language checks, and are where a new rule most often
breaks.

| Place | Fails as | Settled by |
|---|---|---|
| An index or key | `undefined`, `KeyError`, a panic | A bound check, a lookup that returns an option, `noUncheckedIndexedAccess` |
| A branch over cases | Falling through in silence | An exhaustive match, or a default that throws |
| A loop or recursion | Never ending, a stack overflow | A measure that shrinks on each step, or a limit |
| A division or modulo | `NaN`, `Infinity`, a zero-division error | A guard on the divisor |
| A parse or conversion | `NaN`, an exception, a value cut short | Validation that returns a result type |
| Null, None, undefined | A type error far from its cause | A non-optional type, or a guard |
| An empty collection | `max([])` raising, `reduce` without a start | A stated result for empty, or a non-empty type |
| A number | Overflow, precision lost above 2^53, floats for money | Bounded integers, and integers for money |
| A boundary | Off by one where `<` meets `<=` | The equal value among the tested inputs |
| Data from before the change | A record that already breaks the new rule: an account below zero when overdrafts are first refused | A statement for what happens to it, and such a record among the tested inputs |
| Two calls at once | Both pass a check and both write: check, then act | A lock, or a conditional update where the data is stored; otherwise an `assumes` statement |
