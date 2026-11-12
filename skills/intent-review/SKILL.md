---
name: intent-review
description: >-
  Review a code change against stated intent, and report each finding with its
  input, what happens, what was expected and where that expectation comes
  from, separating what a run showed from what was only read. Use this
  whenever you review a pull request, a diff or a branch, especially one that
  carries an intent file (intent/*.md) or was written by an agent, and
  whenever the user asks for a review with few false positives, for findings
  that are reproduced, or to check that a change does what it says. Works
  without an intent file too: the review then builds the statements itself.
---

# Review against intent

## Why

A finding makes three claims at once, and each needs its own evidence:

| Claim | What settles it | Its field |
|---|---|---|
| **The input can arrive** | The code that produces the input. Call sites alone do not show it | `arrives` |
| **The behaviour happens** | A run, and only a run. Reading suggests it | `check`, `observed` |
| **The behaviour is unwanted** | Intent: what was asked for, what the author states, or a contract that was there before the change | `then`, `source` |

Reviews go wrong on the third. With no stated intent, a reviewer infers it
from the code, and code agrees with itself. An intent file gives the third
claim something to stand on. This skill reviews against it, and writes each
finding in the same form, so the three claims stay apart and a machine checks
the second.

You are in the position of a proof's author here: not trusted. A finding is a
statement that the code breaks, and `intent_check.py` runs the check you give
for it.

## 1. Get the statements

**With an intent file,** read its `check` lines first: they are shell commands,
and you are about to run them. Then run the checker, before you write any file
of your own into the repository, and read its report before the code:

```
python3 "${CLAUDE_SKILL_DIR}/../intent/scripts/intent_check.py" intent/<name>.md --base <base branch> -v
```

(The script is in the `intent` skill's folder, beside this one.) Its problems
are your first findings: a check that fails, a check that passes without the
change, a quote the request does not hold. Its notes say whether the history
shows that the statements came before the code, and which statements changed
afterwards. Statements that arrived in one commit with the code show nothing
either way. Format and rules are in `../intent/references/format.md`.

**Without one,** write the statements yourself, in the same format. The request
is the pull request's title and description, and the issue it links.

## 2. Ask four questions, in this order

The checker has done what a machine can. These are what a reader adds.

**Are the statements the right ones?** The author wrote both the statements
and the code, so their agreeing shows little. Compare the statements with the
request.

- A statement weaker than the request: it forbids the bad outcome and does
  not require the good one, or its `given` is narrower than what was asked.
- A part of the request with no statement.
- `inferred` statements. Is each one a fair reading?
- An `assumes` statement that the code itself contradicts: a caller that
  passes what it rules out.
- Statements the checker's note says changed after the code.

**Does each check test its statement?** A check can pass and test something
else. Read it.

- Do its inputs cover `given`, or one corner of it?
- Does it assert `then`, or whatever the code returns?
- Why does it fail without the change? `-v` shows the output. An import error
  is thin evidence.
- Can it fail at all? Break the code it guards, in a copy, and run it. A check
  that still passes is empty, and that run is your evidence.

**Can a statement be broken?** For each `checked` statement, look for a
counterexample and run it: the boundary of each changed condition, empty and
one and many, zero and negative, the largest value, data written before the
change, two calls at once, and the places where code gives no answer
(`../intent/references/forms.md`, last table). A passing run never clears
code. A failing one is a finding with its input.

**Can other input arrive?** For each `assumes` statement, and each `given`
narrower than what the function accepts, find the code that produces the
input. If something outside can reach it unchecked, that is a finding. If the
producer rules it out, say which line does.

## 3. Write each finding as a statement the code breaks

```markdown
## F1 A charge of the whole balance is refused
- kind: keeps
- state: refuted
- given: a balance of 5 and an amount of 5
- then: the charge is taken and the balance is 0
- observed: the charge is refused and the balance stays 5
- arrives: `bill_review` charges 2 for a small review (credits.py:27), so any
  account holding exactly 2 credits
- source: existing: credits.py:11, which took every amount
- check: `python3 -m unittest review.test_whole_balance`
```

- `given` is the input, `observed` what happens, and `then` what was expected.
- `arrives` says how the input gets there: the line that produces it. Where
  the repository does not show it, write `not shown:` and what is missing. A
  behaviour that was run on an input nobody showed to arrive is a question
  about the input.
- `check` exits 0 only when the expectation holds, so it fails now and passes
  once fixed. The author can use it to check the fix.

**The kind says what was broken.**

| Kind | The finding |
|---|---|
| `keeps` | The behaviour held before the change. With `--base` the checker confirms the regression |
| `changes` | The request or the author promised the behaviour, and the change does not deliver it |
| `assumes` | An assumption of the author's is false: the check shows an input it rules out arriving |

**The source decides whether it is a defect or a question.**

| `source` | The expectation comes from | It is |
|---|---|---|
| `request` | What was asked, quoted | A defect: not what was asked |
| `author` | What the change itself states: a statement of its intent file, its description, a comment it adds, as `path:line` | A defect: the code does not do what its author says |
| `existing` | A test, a document, a caller or the code as it was before the change, as `path:line` at the base | A defect where the request and the author are silent on it. A question, with the input, where either states the new behaviour: both may be right |
| `inferred` | Your reading | A question. Your reading is not a contract |

**Other statements belong in the same file.**

- **A better check for one of the author's statements.** Where their check was
  thin and yours passes with the change and fails without it, add the
  statement as `checked`. That is evidence for the change, and worth offering.
- **What you could not settle,** as `open`, with what would settle it.

## 4. Let the checker judge the findings

- **Put your check files in a folder of their own** at the repository's root,
  untracked, such as `review/`.
- **Write the statements to one file,** such as `review/findings.intent.md`,
  with the request quoted at the top.
- **Name the author's tests and your folder under `tests`:**
  `- tests: tests/, review/`. The checker takes untracked files out with the
  change unless `tests` names them.

Run the checker over that file with `--base`, and label each finding by what
it shows:

| Label | Meaning |
|---|---|
| **Reproduced** | `refuted`, and the check fails with the change |
| **Regression** | Reproduced, and the check passes with the change taken out |
| **Read, not run** | `open`: you traced it and could not run it. Say why |

A finding whose check passes is not a finding: the checker reports it, and you
drop it or look again. A suspicion you could neither show nor rule out stays
on the list as open. Dropping needs evidence as much as posting does.

## 5. Report

Answer what was asked first. If that was "can I merge this", give your
recommendation, and leave the decision with the person who asked.

Then, in this order:

1. the statements that are wrong or missing, as only a person can settle
   those;
2. the findings, the reproduced ones first, each with its input, what
   happens, what was expected, its source, and whether its input was shown to
   arrive;
3. the questions and the open statements;
4. what you did not check.

A review that found nothing has not shown the change correct: it has shown
these statements on these inputs.

Keep your check files out of the change unless the author wants them. Offer
them: a check that fails now and passes when fixed is the most useful part of
a finding.
