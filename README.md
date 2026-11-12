# skill-intent-statements

Two skills for coding agents, and one script that uses no model.

- **`intent`** has an agent write a change as statements of intent, then
  checks a machine runs, then the code, and record which statements were
  checked, which are only assumed and which nobody asked for.
- **`intent-review`** has an agent review a change against those statements,
  and write each finding in the same form: its input, what happens, what was
  expected, and where that expectation comes from.
- **`intent_check.py`** reads the statements, verifies what code can verify,
  and runs each statement's check with the change and with the change taken
  out.

**Nothing here shows an improvement yet** (see [Status](#status)).

- On three seeded cases, an agent without the skills did as well as one with
  them, at half the tokens.
- On nine known bugs in real changes, agents on three models kept no more of
  them out of their own code with the `intent` skill than without it.
- A reviewer given statements written before the code found no more of 44
  known bugs, and posted more false findings. Given a statement that covers
  the bug, it found nearly all of them.

So a right statement helps, and these skills do not yet get an agent to write
it from a one-line request. The tests are written up in
[Does it help code quality if agents encode their intents?](https://rapidreview.dev/blog/does-it-help-code-quality-if-agents-encode-their-intents)

## Why

A reviewer gets finished code and no specification. It infers what the code is
for from the code, and code agrees with itself. The author has the request, in
the words of the person who made it, at the moment the change is written. That
is the cheapest point at which to state intent, and the only one where it
does not have to be guessed.

The design takes four ideas from proof assistants such as
[Lean](https://lean-lang.org), and none of the proving.

| In a proof assistant | Here |
|---|---|
| **The statement is fixed before the proof** | The statements are written before the code, each as `given` and `then`. A statement written from finished code is met by construction. The script reads git's history and reports whether it shows that order, and which statements changed afterwards |
| **A small kernel checks every proof,** and whatever wrote it is not trusted | The agent proposes. The project's test runner and `intent_check.py` decide |
| **Proved, refuted and open are three states,** and the first two carry evidence | `checked` has a check that passes, `refuted` one that fails, and `open` a reason. Nothing is dropped in silence |
| **`sorry` marks what was assumed** | `open` statements and `inferred` sources are listed in every report |

Two things no proof assistant gives, and this does not either:

- **Whether a statement is the right one.** A prover shows that code meets its
  statement, not that the statement is what was wanted. That stays with the
  person who asked, so the statements are kept short enough to read.
- **Bugs outside the inputs that ran.** A passing check clears those inputs
  and no others.

## What the checker verifies

For each statement in an intent file:

| | |
|---|---|
| Its source | A quote attributed to the request is in the request. A file and line named as an existing source were there at the base |
| Its state | `checked` and `refuted` have a check, `refuted` says what was observed and how its input arrives, and `open` says why |
| With the change | A `checked` statement's check passes, and a `refuted` one's fails |
| With the change taken out | A check for behaviour the change brings fails, and one for behaviour it keeps passes |

The last row is what makes `checked` mean something. A test that passes with
and without the change does not test the change, and agents write such tests.
The script sets every file that differs from the base back to its base
version, leaves the tests alone, runs the checks, and puts the working tree
back, also when it is interrupted.

The format and every rule are in
[`skills/intent/references/format.md`](skills/intent/references/format.md).
An example is this repository's own:
[`intent/first-version.md`](intent/first-version.md).

```
python3 skills/intent/scripts/intent_check.py intent/first-version.md --run
```

That verifies the statements and runs each check on the working tree. On a
branch, add `--base <ref>`, such as `--base origin/main`, to run each check
again with the change since `<ref>` taken out.

It needs Python 3.9 or later and git.

## Install

**As a plugin,** in Claude Code 2.1.275 or later:

```
/plugin install skill-intent-statements --marketplace rapidreview-dev/skill-intent-statements
```

The skills are then `/skill-intent-statements:intent` and
`/skill-intent-statements:intent-review`, and Claude also loads them by itself
when a task fits their descriptions.

**In a repository,** for cloud sessions, which do not load plugins, and for
other agents that read skill folders: copy both folders, side by side.

```
cp -r skills/intent skills/intent-review <your-repository>/.claude/skills/
```

`intent-review` runs the script from `intent`'s folder, so the two stay
together.

**In CI,** so that the check does not depend on the author having run it: the
workflow is at the end of `format.md`.

## Where the design comes from

The design rests on published work and on one measurement of the `intent`
skill itself ([Status](#status)). The published results are why the skills
say what they say. None of them is a measurement of these skills.

| The skills say | Because |
|---|---|
| Never write a statement from the code | Statements a model wrote with the finished change in hand described a known bug as intended for 8 of 44 bugs. Written before the code, they did so for none ([Status](#status)) |
| Search for a counterexample; don't prove | With a Lean model of Cedar, 4 bugs were found by proving and 21 by random and property-based testing (Disselkoen et al., 2024). The best model on VERINA wrote correct Lean code for 72.6% of tasks and a proof for 4.9% (Ye et al., 2025) |
| Run with and without the change | ChangeGuard compares executions before and after a change: 77.1% precision and 69.5% recall on behaviour-changing changes, where the projects' own tests reached 7.6% recall (Gröninger et al., 2025). Testora reads each difference against the pull request's stated intent (Pradel, 2026) |
| State intent as something executable | Postconditions a model wrote from documentation caught 64 Defects4J bugs (Endres et al., 2024) |

- Bursuc, S., et al. (2025). A benchmark for vericoding: formally verified
  program synthesis. https://arxiv.org/abs/2509.22908
- Disselkoen, C., et al. (2024). How we built Cedar: a verification-guided
  approach. FSE Companion '24. https://arxiv.org/abs/2407.01688
- Endres, M., Fakhoury, S., Chakraborty, S., & Lahiri, S. K. (2024). Can large
  language models transform natural language intent into formal method
  postconditions? FSE 2024. https://arxiv.org/abs/2310.01831
- Gröninger, L., Souza, B., & Pradel, M. (2025). ChangeGuard: validating code
  changes via pairwise learning-guided execution. FSE 2025.
  https://arxiv.org/abs/2410.16092
- Pradel, M. (2026). Testora: using natural language intent to detect
  behavioral regressions. ICSE 2026. https://arxiv.org/abs/2503.18597
- Ye, Z., et al. (2025). VERINA: benchmarking verifiable code generation.
  https://arxiv.org/abs/2505.23135

## Limits

- **A check can pass and test something else.** The script sees that a check
  fails without the change, not that it asserts its statement. Reading the
  check is the reviewer's second question.
- **A check can fail without the change for a thin reason,** such as an
  import of a module the change adds.
- **The request is as the author pasted it.** The script verifies quotes
  against those lines. That the lines are the request, the person who asked
  can see and the script cannot.
- **Running checks runs code.** Use the script only where you would run the
  change's own tests.
- **Linux and macOS.** Windows is untried.

## Licence

MIT. See [`LICENSE`](LICENSE).

## Status

- **Built:** the two skills, the script and its tests
  (`python3 -m unittest discover -s tests`).
- **Tried on 2026-11-10,** on three seeded cases (`evals/`, in the layout
  `claude plugin eval` reads), each run once by a fresh agent with the skill
  and once without.

  | Case | Without the skill | With the skill |
  |---|---|---|
  | Write: refuse a charge that would overdraw | Right on all 4 hidden probes. 105k tokens, 3.8 min | Right on all 4. Its intent file passes the checker: 8 statements checked, 3 open. 183k tokens, 11.0 min |
  | Write: rewrite `slugify`, behaviour unchanged | Same as the old loop on every input tried. 95k tokens, 2.8 min | The same. Its intent file passes the checker: 4 checked, 2 open. 181k tokens, 14.4 min |
  | Review: a change with five planted problems | All 5 found, and one more that was not planted. 104k tokens, 3.4 min | All 5 and the same sixth. The checker confirmed each finding's check, two as regressions. 212k tokens, 13.0 min |

  - **The outcome was the same.** The agent without the skills avoided every
    planted trap, so these cases cannot show an improvement.
  - **The skills cost about twice the tokens and three to five times the
    time.** What they added is the record: statements with their sources,
    evidence a script verified, and findings that come with a check.
  - **It is one run each, with no bar set beforehand,** and the runs with a
    skill were not blind. The cases then sat inside the skill folders: one
    agent saw the graders' file names, and one opened a case's expected
    outcome. The cases are at the repository's root now.
  - **The skills were then revised** from the three agents' notes. No agent has
    run the revised text.
- **Measured since, in four tests** on 54 real changes from six open-source
  projects (hono, httpx, cobra, urfave/cli, click and ky). 42 of them hold 44
  bugs that their projects later fixed, and each change came with one line of
  request: its commit subject. For each test, the question, the cases and
  what would count were written down before any model was called. The tests'
  records are not public. The post linked above describes them.
- **On what the statements say** (2026-11-10). A model given the `intent`
  skill's text wrote statements for the 54 changes, once before the code and
  once after it.

  | Statements written | Cover a bug exactly | State the bug as wanted |
  |---|---:|---:|
  | Before the code, from the subject line and the base | 15 of 44 | 0 |
  | After the code, with the diff | 14 of 44 | 8 |

  - **Before the code,** a statement fixed the behaviour for the bug's own
    case in 15 of 44 changes, so the bug breaks it as written.
  - **After the code,** the statements described the bug's behaviour as
    wanted for 8. That is the order this skill warns against.
  - The checker accepted all 108 intent files, 105 at the first ask.
- **On the checks** (2026-11-10). For each of the 15 bugs a
  statement covered exactly, an agent wrote a test from the statement alone,
  then ran it on the change as its author committed it.
  - **The check caught the bug in 11 of the 15:** it fails on the change as
    written and passes with the later fix, by `intent_check.py --base`.
  - **All 15 fail on the change as written.** Four stay red with the fix:
    three on a statement that was wrong or said too much, one on a second
    copy of the same mistake.
  - **The cost showed too.** Of 29 checks, 19 were red on the change as
    written: 13 pointing at the bug, 1 at an older fault, and 5 because the
    statement was wrong. Those five each quoted or cited a source, and went
    wrong in the detail the writer added to it.
  - **Limits of both counts:** the bugs are people's, so neither shows what
    an agent's own code would gain; the changes had only a subject line; and
    the models may have seen these public repositories in training.
- **On an agent's own code** (2026-11-11). Agents on three models wrote eight of those changes from the
  subject line in a plain tool loop, with the `intent` skill and without it.
  Hidden checks then read the cases of nine known bugs. The bar was set
  beforehand. Opus ran once, and Haiku and DeepSeek four times.

  | Model | Bug cases right, plain | With the skill | Spend with the skill |
  |---|---:|---:|---:|
  | Opus 5.5 | 9 of 9 | 9 of 9 | 2.4 times |
  | Haiku 5.5 | 23 of 36 | 25 of 36 | 2.4 times |
  | DeepSeek V4.1 Flash | 25 of 36 | 23 of 36 | 1.1 times |

  - **No gain shows on any model,** and no harm. Opus leaves nothing to
    gain. Haiku and DeepSeek get about a third of the cases wrong either
    way.
  - **One run says little.** After the first run Haiku's skill arm was behind
    on three bugs and ahead on one. Over four it is ahead on three and behind
    on one, and neither is more than chance gives.
  - **One bug came back as people wrote it, again and again:** a flag name
    repeated between two levels in urfave/cli's help, in 13 of the two
    models' 16 runs. No skill run of theirs stated that case, and three
    intent files name it in a note and leave it.
  - **A case the agent stated nearly always came out right:** 45 of 48 by the
    bug's own check. Haiku and DeepSeek stated about three cases in five,
    and Opus all nine.
  - **With the skill, Haiku's own tests reach the bug's case more often,** 21
    of 36 against 15. No bar was set for this, and it did not show in the
    cases right.
  - **The record was kept:** 66 of the skill's 72 runs left an intent file,
    and the checker accepts 62.
  - **Limits:** nine bugs chosen in the skill's favour, as a skill-written
    statement had covered each; a plain tool loop and not a product agent,
    whose limits ended a quarter of DeepSeek's runs; one run of Opus.
- **On a reviewer given the statements** (2026-11-12). Sonnet 5.5 and Haiku 5.5 reviewed the 54 changes
  three times each, with the statements beside the change as its claims.
  Bugs found, of 44, summed over three runs:

  | Reviewer | No statements | Written before the code | Written after the code | One statement told the bug |
  |---|---:|---:|---:|---:|
  | Sonnet 5.5 | 84 | 79 | 76 | 120 |
  | Haiku 5.5 | 50 | 58 | 50 | 116 |

  - **A statement that covers the bug helps both reviewers find it.** That
    arm is a ceiling: its statements were written knowing the bug.
  - **Statements written before the code, from a subject line, do not.**
    Neither reviewer finds more bugs by the bar set beforehand. Where they
    cover the bug, Haiku gains a little.
  - **They add findings on clean changes,** twice as many for Sonnet, and
    most of the addition is wrong: the reviewer holds the code to a
    statement nobody asked for.
  - **Statements written after the code** are not shown to hide bugs.
  - **Limits:** this is a reviewer handed statements, not the
    `intent-review` skill; and the statements are a model's, from a subject
    line, not an author's with the request in hand.
- **Not measured:** the `intent-review` skill itself, against a reviewer
  without it. Statements written by an author who has a real request. The
  `intent` skill on bugs no statement covered, or loaded by a product agent
  as a skill.
