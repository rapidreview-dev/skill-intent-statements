---
name: intent
description: >-
  Write a code change as statements of intent, checks a machine runs, and then
  the code, in that order, and record which statements were checked, which are
  only assumed and which nobody asked for. Use this whenever you implement a
  feature, fix a bug, change behaviour or refactor code that will be reviewed,
  merged or handed on, even when the user only says "implement X" or "fix Y"
  and never mentions intent, specs, properties or tests. Also use it when asked
  to formalize requirements, write a spec or contract for a change, add
  property-based tests, or make a change easier to review. Not for changes
  without behaviour: prose, comments, formatting, renames.
---

# Intent: say what a change is for, in a form a machine can check

## Why

A reviewer, human or agent, gets finished code and no specification. It has to
guess what the code is for from the code, and code always agrees with itself.
You have what the reviewer lacks: the request, now, in the words of the person
who made it.

So write it down as statements before the code exists, tie each statement to a
check a machine runs, and say plainly which statements nothing checks. This is
how a proof assistant divides the work, without the proofs:

- **The statement is fixed before the proof.** A statement written after the
  code describes the code. It then catches nothing, because the code meets it
  by construction.
- **The author is not trusted, and a small checker is.** You propose. The
  project's test runner and `scripts/intent_check.py`, which use no model,
  decide.
- **Checked, refuted and open are three states.** The first two carry
  evidence. `open` is the honest one: assumed, not checked, and said so.
- **No checker can say that a statement is the right one.** That stays with
  the person who asked. Keep the statements few and plain, so that person can
  read them in a minute.

## The order of work

### 1. Record the request

Create `intent/<short-name>.md` (or follow the repository's own place for
these). Start it with the request, word for word, as a quotation: the user's
message, or the issue's text. Don't paraphrase it. The checker verifies every
quote you later attribute to the request against these lines, and the person
who asked recognises their own words.

### 2. Write the statements, before any code

Split the request into statements. Each is one behaviour:

- `given`: the inputs it covers, and where they come from;
- `then`: what must hold for them.

Write `then` so that a wrong implementation breaks it. A statement that only
forbids ("the balance is never negative") is met by code that does nothing, so
pair it with what must happen ("a charge within the balance is taken").

**Give each statement a kind.**

| Kind | It says |
|---|---|
| `changes` | What this change brings: new or corrected behaviour, or something the request asks of the code itself ("use a regular expression") |
| `keeps` | Behaviour that must stay as it was. A refactor is mostly `keeps`, and almost every change has some: what the touched code does for its other callers |
| `assumes` | Something the code relies on and does not check itself, about its inputs or about where it runs. Name what guarantees it: a type, a validator at the boundary, the only caller |

Where input comes from outside (a request, a webhook, a file, the
environment), something has to check an assumption. Assuming it is how
"works as intended" turns into "can be used otherwise".

**Say where each statement comes from,** in `source`:

- `request`: quote the words it rests on.
- `existing`: a test, a document, a caller or a type that was in the
  repository before the change, as `path:line`. The line is the one before
  your change.
- `inferred`: nobody said it. You concluded it, and you say from what.

Never take a statement from the code you are about to write, or have written.
When a model wrote statements with the finished code in hand, they described
a known bug as intended for 8 of 44 bugs: the code vouched for itself.

**Keep what was asked apart from what you chose.** The request often gives the
behaviour and leaves its form to you: "refused" does not say whether by an
exception or a return value. The behaviour is a `request` statement, and your
choice of form is its own `inferred` one. Sourcing both to the request settles
the question without anyone seeing it.

**Where the request is unclear,** ask if someone is there to answer and the
answer changes the code. Otherwise choose a reading and mark the statement
`inferred`, so it surfaces in the report. Don't settle an ambiguity silently in
the code.

**Walk the places where the new code may give no answer, or a wrong one.** For
each function you add or change:

- an index or key that may be absent, a case no branch covers, a loop or
  recursion that may not end, a division, a conversion that can fail, a null,
  an empty collection, a number too large;
- data that already exists and breaks the new rule: a record written before
  the change;
- two calls at once, where the code checks and then writes.

A proof language refuses code that skips the first group. Other languages fail
there at run time. Each place gets one of three: the code handles it and a
statement says how; an `assumes` statement rules it out; or a type makes it
impossible.

**Keep the list short enough to read.** A statement earns its place when its
reader would decide differently for knowing it, or a check guards it.

- Cases of one behaviour are one statement, with several tests in its check.
- What the walk found and nobody needs to decide goes in a `note`.
- A one-function change with more than about six statements usually has
  cases listed as statements.

**Until a statement has its check,** write `state: open` with
`because: its check is not written yet`. A statement is what it says: `kind`,
`given`, `then` and `source`. The rest is evidence, and adding evidence later
changes no statement.

**Commit the statements first, if you may commit.** Many sessions commit only
when asked: follow that. Where you do commit, the statements go in on their
own before the code, and the checks may go with the code. The checker reads
the history and reports whether it shows that order, and which statements
changed afterwards. Without commits, the order is your word, and the report
says so.

### 3. Write each check, and see it fail

A check is a command that exits 0 only when its statement holds. Use the
project's own test runner, and name the tests where the runner allows it;
`references/format.md` has the command for each common runner. Choose the
strongest form that fits; `references/forms.md` has each with examples.

| Form | Fits when |
|---|---|
| A type | The bad state can be made impossible to write down |
| A property over generated inputs | `then` holds for a whole class of inputs, which is the usual case for "given any…" |
| A comparison with the old code | The statement is a `keeps`: run both on the same inputs |
| An example | One named input matters, such as the one from the bug report |
| A command over the code | The request asks something of the code itself, and `grep` or a linter can tell |
| A proof | The project already uses a prover. Otherwise don't: models prove little |

Run each check of a `changes` statement before writing the code. It has to
fail, and on what the old code does, not on a name that is missing: look a new
name up inside the test, so the file still loads without the change. A check
that already passes does not test the change, and a test written to match
finished code tends to assert whatever the code returns.

Where a check runs fewer inputs than `given` covers, say in the statement what
it runs. "Any string" cannot be generated; "every code point, and 20,000
seeded strings" can.

### 4. Write the code

Now the code, until the checks pass. Change the code, not the checks.

### 5. Try to break it before calling it done

A passing check clears the inputs it ran, and no others.

**Look for a counterexample.** For each statement, try the inputs most likely
to break it:

- the boundary of every condition you wrote or changed: where `<` became
  `<=`, the equal value;
- empty, one and many; zero and negative; the largest value; a repeated item;
- everything from the walk in step 2.

An input that finds something becomes a test. One that finds nothing need not.

**Break the code on purpose, once for each check.** Change the condition you
wrote, or swap in the wrong implementation a tired author would write, and see
the check fail. This matters most for `keeps`: the checker shows that a
`changes` check depends on the change, and nothing shows that a `keeps` check
can fail at all. A comparison over too few inputs passes whatever the code
does.

A counterexample means the code is wrong, or the statement was (see below).

### 6. Run the checker

```
python3 "${CLAUDE_SKILL_DIR}/scripts/intent_check.py" intent/<short-name>.md --base <branch this merges into>
```

(The script is `scripts/intent_check.py` in this skill's folder.) It runs each
check twice. With the change, a `checked` statement must pass. With the change
taken out, where every file that differs from the base is set back except the
tests, a `changes` check must fail and a `keeps` check must pass. It puts the
working tree back afterwards. If it is ever cut off, run it again and it
restores the tree first.

Uncommitted work counts as the change, so `--base main` is right on `main`
itself too.

When it reports a problem, fix the cause. Don't reword a statement to quiet it.

### 7. Report what holds, what is assumed and what nobody asked for

Add `--format markdown` and put that output in the pull request's description,
or in your final message, with the command that produced it. Don't retype the
states from memory: the table comes from the checker, and it already lists the
open statements with their reasons, the inferred ones, and what the history
shows.

Add only what the table cannot say, a line each:

- for each `inferred` statement, the choice you made and its alternative;
- any statement you changed after writing the code, and why;
- what the request asked that no statement covers, such as "easier to read".

## The file

```markdown
# Intent: Refuse a charge that would overdraw

> Credits must never go negative. A charge that would overdraw is refused,
> and the balance stays as it was.

- tests: tests/, conftest.py

## S1 A charge within the balance is taken
- kind: keeps
- state: checked
- given: a balance b ≥ 0 and an amount a with 0 ≤ a ≤ b, the whole balance included
- then: the new balance is b − a
- source: existing: tests/test_credits.py:12
- check: `pytest tests/test_credits.py::test_takes_a_charge tests/test_overdraw.py::test_takes_the_whole_balance -q`

## S2 A charge above the balance is refused
- kind: changes
- state: checked
- given: a balance b ≥ 0 and an amount a > b
- then: the charge is refused (S3 says how), and the balance is still b
- source: request: "A charge that would overdraw is refused, and the balance stays as it was"
- check: `pytest tests/test_overdraw.py::test_refuses_an_overdraw -q`

## S3 A refusal is the exception InsufficientCredits
- kind: changes
- state: checked
- given: a charge that S2 refuses
- then: `charge` raises `InsufficientCredits` and returns nothing
- source: inferred: the request says "refused" and not how. `charge` returns
  the balance as a bare number, so no return value is free to mean refused
- check: `pytest tests/test_overdraw.py::test_a_refusal_raises -q`

## S4 Amounts are whole and not negative
- kind: assumes
- state: open
- given: every caller of `charge`
- then: `amount` is an integer ≥ 0
- source: inferred: `bill_review` is the only caller, and it passes a constant
- because: nothing checks it where a request comes in. A schema on the route would.
```

`tests` names the files that stay as they are when the change is taken out:
the tests, and whatever only they need. `references/format.md` has every field
and every rule the checker applies.

## When a statement and the code disagree

- **The code is wrong.** Fix the code.
- **The statement cannot be met in this change.** Keep it. Call it `refuted`,
  with what happens instead and a check that fails, or `open` with the reason.
  Report it.
- **The statement was wrong,** because you misread the request. Change it, and
  say in the report which one and why.
- **You found a difference that no statement covers.** If the request's words
  cover it ("exactly the same"), it is a `refuted` statement, however unlikely
  the input. If one of your `assumes` statements rules the input out, put it
  in that statement's `note` and name it in the report.

The failure this skill exists to prevent is one more move: quietly weakening a
statement until the code meets it. The reader would then see checks pass
against a specification written from the code.

## Sizing it

- **A one-line fix** gets one statement and one check. That is the test that
  fails before the fix and passes after, which the fix needed anyway.
- **A change nobody can run a check for here** (no runner, a service that is
  not there) gets `open` statements. That is still more than a reviewer has
  without them.
- **Exploration and prototypes** need none of this until they are to be kept.
- **Don't add a property-testing library unasked.** A new dependency is the
  owner's decision. Propose it, and write the loop meanwhile.
- **A reader without this skill** can still run the checker: it is one file
  with no dependencies, and a repository that wants the check in CI keeps a
  copy of it.
