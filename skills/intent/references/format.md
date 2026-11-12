# The intent file, and what the checker does with it

One file for each change, in Markdown, so that a person reads it rendered and
`scripts/intent_check.py` reads it too.

## Contents

- [The header](#the-header)
- [A statement](#a-statement)
- [States, and the evidence each needs](#states-and-the-evidence-each-needs)
- [Sources](#sources)
- [What the checker runs](#what-the-checker-runs)
- [What the history shows](#what-the-history-shows)
- [The command](#the-command)
- [One test by name](#one-test-by-name)
- [Things that go wrong](#things-that-go-wrong)
- [In CI](#in-ci)

## The header

```markdown
# Intent: <what the change is for>

> The request, word for word. It may run over
> several lines, each starting with ">".

- tests: tests/, *.test.ts, vitest.config.ts
```

- **The title** starts with `# Intent:`.
- **The request** is every line that starts with `>` above the first
  statement. For a pull request written by someone else, it is the pull
  request's title and description.
- **`tests`** is needed for `--base`. It lists, separated by commas, the files
  that stay as they are when the change is taken out: the tests, their
  fixtures and helpers, and configuration only they need. The patterns work as
  in `.gitignore`: `tests/` is the folder, `*.test.ts` matches the name at any
  depth, `**/` crosses folders, and `*` stays inside one.
- Other text above the first statement is ignored.

## A statement

```markdown
## S2 A charge above the balance is refused
- kind: changes
- state: checked
- given: a balance b ≥ 0 and an amount a > b
- then: `charge` returns `refused`, and the balance is still b
- source: request: "A charge that would overdraw is refused"
- check: `pytest tests/test_credits_properties.py::test_refuses_an_overdraw -q`
```

- **The heading** is an id (letters, then digits: `S1`, `F3`) and a title.
  Every `##` heading is a statement.
- **A field** is a list item, `- key: value`. A value continues on following
  lines that are indented. A key the checker does not know is a problem, so a
  typo does not pass unseen.

| Field | Needed | |
|---|---|---|
| `kind` | always | `changes`, `keeps` or `assumes` |
| `given` | always | The inputs the statement covers, and where they come from |
| `then` | always | What must hold for them |
| `source` | always | Where the intent comes from; see below |
| `state` | always | `checked`, `refuted` or `open` |
| `check` | `checked`, `refuted` | A command that exits 0 only when the statement holds. Backticks around it are optional, and it may name several tests |
| `observed` | `refuted` | What happens instead |
| `arrives` | `refuted` | How the input gets there: the line that produces it, or `not shown:` and what is missing |
| `because` | `open` | Why nothing checks it, and what would |
| `note` | never | Anything else |

The first four are what the statement says. The rest is the evidence for it:
adding a check, a note or a reason later changes no statement.

## States, and the evidence each needs

| State | Means | Evidence |
|---|---|---|
| `checked` | A run shows it holds | Its check passes |
| `refuted` | A run shows it does not hold | Its check fails, and `observed` says what happens instead |
| `open` | Assumed, and not checked | `because` |

A statement is not dropped because it is inconvenient. It moves to `refuted`
or `open`, with its reason.

## Sources

`source` starts with one of four words. An author uses the first three, and a
reviewer all four.

| Source | Form | The checker verifies |
|---|---|---|
| `request` | `request: "the words it rests on"` | Each quoted passage is in the request, whatever its case, spacing and quote marks |
| `existing` | `existing: path` or `path:line` or a URL, then a note | The file is there and has that line. With `--base` it reads the base's version, so the line is the one before the change, and a file the change added is refused: that would be the change vouching for itself |
| `author` | `author: path` or `path:line`, then a note | The file is there and has that line. For a review: what the change itself states, in its intent file, its description or a comment it adds |
| `inferred` | `inferred: from what` | That a reason is given. The report lists every inferred statement, for a person to confirm |

One file is checked for each source: the first thing after the word.

## What the checker runs

Each check runs from the repository's root, with `CI=true` set so that test
runners neither wait for changes nor write missing snapshots.

| Statement | With the change (`--run`) | With the change taken out (`--base`) |
|---|---|---|
| `changes`, `checked` | passes | **fails**: otherwise the check does not show what the change does |
| `keeps`, `checked` | passes | **passes**: it held before |
| `assumes`, `checked` | passes | not run |
| any kind, `refuted` | **fails** | `keeps` only: passes, which makes it a regression |
| `open` | not run | not run |

- **A check that cannot run shows nothing.** Exit 126 or 127, or running out
  of time, is a problem wherever it happens. It never counts as a check
  failing.
- **Taking the change out** sets every file that differs from the base back
  to its base version, deletes those the change added, and leaves alone the
  intent file, the files under `tests`, and whatever git ignores. Uncommitted
  work counts as part of the change.
- **The base** is where the branch left the ref you name: `--base origin/main`
  means the merge base of `origin/main` and `HEAD`.
- **Afterwards the working tree is put back,** also when a check fails or the
  run is terminated. The files are first copied into `.git/intent-check/`. If
  a run is killed outright, the next run of the script, with any arguments,
  puts them back before doing anything else.

## What the history shows

With `--base`, the checker reads git's history of the intent file since the
base and adds one note to the report:

- whether the statements were first committed before the code (on their own,
  or with files under `tests` only), together with other files, or not at all;
- which statements changed since in what they say (`kind`, `given`, `then`,
  `source`), and which were added or removed.

It is a note, not a problem. A statement may change for a good reason, and the
author's report says which and why. Statements committed together with the
code, or not committed, show nothing either way.

## The command

```
python3 scripts/intent_check.py FILE... [--run] [--base REF]
        [--format text|markdown|json] [--timeout SECONDS] [-v]
```

| | |
|---|---|
| no option | Reads the file and reports what is malformed |
| `--run` | Also runs each check with the change |
| `--base REF` | Also runs checks with the change taken out. Implies `--run` |
| `--format markdown` | A table for a pull request's description, then the refuted and the open statements with their reasons, the inferred ones, and the notes |
| `--format json` | Everything, for another tool |
| `-v` | Shows the last 25 lines of each check's output, not only of the unexpected ones |

It exits 0 when everything is as stated, 1 when something is not, and 2 when
it could not do the job. It needs Python 3.9 or later and git, and nothing
else.

## One test by name

A check may name several tests in one command.

| Runner | One test |
|---|---|
| pytest | `pytest tests/test_credits.py::test_refuses_an_overdraw -q` |
| unittest | `python3 -m unittest tests.test_credits.Credits.test_refuses_an_overdraw` |
| Vitest, Jest | `npx vitest run tests/credits.test.ts -t "refuses an overdraw"` |
| node:test | `node --test --test-name-pattern="refuses an overdraw" tests/credits.test.js` |
| Go | `go test ./credits -run '^TestRefusesAnOverdraw$'` |
| Cargo | `cargo test refuses_an_overdraw -- --exact` |

## Things that go wrong

- **A filter that matches no test can pass.** `go test -run` with a name that
  matches nothing prints "no tests to run" and exits 0, and other runners skip
  what a name filter does not match. For a `changes` statement `--base`
  catches this, as the check passes without the change too. For a `keeps`
  statement nothing does, so read the first run's output for the test's name
  (`-v`).
- **A check that fails without the change for a thin reason.** If a test file
  imports a name the change adds, every test in it fails without the change:
  thin evidence for `changes`, and it breaks a `keeps` check in the same file.
  Import the module and look the new name up inside the test
  (`credits.InsufficientCredits`), so the file loads either way and the test
  fails on what the old code does.
- **Nothing shows that a `keeps` check can fail.** It passes with and without
  the change by design. Break the code on purpose and see it fail.
- **Files you add that are not the change,** such as a reviewer's checks, are
  taken out with it unless `tests` names their folder.
- **Configuration the tests need** (a new runner config, a fixture) belongs
  under `tests`, or the base run fails for want of it.
- **A `refuted` statement's check fails by design.** Keep it out of the suite
  that CI runs, or expect that suite to be red until the code is fixed.
- **Only run this where you would run the change's own tests.** The checks
  are shell commands from the file.

## In CI

```yaml
# .github/workflows/intent.yml
on: pull_request
jobs:
  intent:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      # ...install what the project's tests need...
      - run: |
          files=$(git diff --name-only --diff-filter=AM origin/${{ github.base_ref }}...HEAD -- 'intent/*.md')
          [ -z "$files" ] || python3 scripts/intent_check.py $files --base origin/${{ github.base_ref }}
```

The script is one file with no dependencies, so the repository keeps a copy of
it, here as `scripts/intent_check.py`. This is the one place where the check
does not depend on the author having run it.
