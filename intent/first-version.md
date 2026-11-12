# Intent: Skills for stating a change's intent and reviewing against it

> Asked for: skills or a plugin with which coding agents write code, tests and
> a formal statement of intent, building on proof assistants such as Lean and
> on research into defect detection. The aim: better code generation by agents
> and better review by agents.

- tests: tests/

This is the repository's own intent file, in the format the `intent` skill it
adds describes. Three things make its evidence thinner than the skill asks for:

- **The request above is a summary.** The words it was made in are not
  reproduced here. S1 to S3 quote the summary, so the script's comparison
  shows that their quotes match it, and nothing about the original.
- **The statements were written after the script and its tests,** because the
  format did not exist before them. That is the order the skill warns against.
  What stands in for it here: the script was broken in thirteen ways, one at
  a time, and the tests failed each time. The list is not in this repository.
- **Everything in this change is new,** so each check fails without the change
  for the plainest reason: the files are not there.

## S1 The repository is a plugin with a skill for writing a change
- kind: changes
- state: checked
- given: an agent that loads plugins, or skill folders copied into a repository
- then: it finds a skill named `intent`, whose steps put the statements before
  the checks and the checks before the code
- source: request: "skills or a plugin with which coding agents write code, tests and a formal statement of intent"
- check: `python3 -m unittest tests.test_plugin.Plugin.test_the_manifests_name_one_plugin tests.test_plugin.Plugin.test_each_skill_is_named_after_its_folder_and_says_when_to_use_it tests.test_plugin.Plugin.test_the_writing_skill_puts_statements_before_checks_before_code tests.test_plugin.Plugin.test_a_skill_copied_into_a_repository_needs_nothing_from_the_plugin`

## S2 There is a skill for reviewing against intent
- kind: changes
- state: checked
- given: the same agent, asked to review a change
- then: it finds a skill named `intent-review`, and every file either skill
  points to is there
- source: request: "better code generation by agents and better review by agents"
- check: `python3 -m unittest tests.test_plugin.Plugin.test_there_is_a_skill_for_writing_and_one_for_reviewing tests.test_plugin.Plugin.test_every_file_a_skill_points_to_is_there tests.test_plugin.Plugin.test_the_example_in_the_writing_skill_is_a_valid_intent_file`

## S3 Agents write better code and better reviews with the skills than without
- kind: changes
- state: open
- given: an agent given a change to write or to review, with and without the skills
- then: with them it leaves fewer defects in what it writes, and reports more
  real defects and fewer false ones in what it reviews
- source: request: "The aim: better code generation by agents and better review by agents"
- because: Not measured. It takes runs with and without the skills on changes
  with known defects, and a bar set before the runs. Three seeded cases, each
  run once with the skills and once without, came out the same either way:
  the agent without them avoided every planted trap too (README, "Status").

## S4 A statement's state must match what its check does
- kind: changes
- state: checked
- given: an intent file whose statements name checks, and `--run`
- then: the script reports a problem for a `checked` statement whose check
  fails, for a `refuted` one whose check passes, and for any state that lacks
  its evidence
- source: inferred: the Lean session's answer, "Proved, refuted and open are
  three states, and the first two each carry evidence"
- check: `python3 -m unittest tests.test_intent_check.Running.test_a_checked_statement_must_pass tests.test_intent_check.Running.test_a_refuted_statement_must_fail tests.test_intent_check.States`

## S5 A check must depend on the change
- kind: changes
- state: checked
- given: `--base`, and a `checked` statement of kind `changes` or `keeps`
- then: the script reports a problem when a `changes` check passes with the
  change taken out, and when a `keeps` check fails there
- source: inferred: the session "Custom defect classifier versus LLMs", on a
  test that "fails on the old code and passes on the new": no opinion is
  involved
- check: `python3 -m unittest tests.test_intent_check.WithoutTheChange`

## S6 A quote attributed to the request must be in the request
- kind: changes
- state: checked
- given: a statement whose source is `request` or `existing`
- then: the script reports a problem when the request does not hold the quote,
  when the file named is not there, and with `--base` when the file was not in
  the base
- source: inferred: a quote that is not in the request vouches for nothing,
  so the script looks for it whole. The alternative is to trust the
  attribution
- check: `python3 -m unittest tests.test_intent_check.Sources`

## S7 A check that cannot run shows nothing
- kind: changes
- state: checked
- given: a check whose command is missing, cannot be executed or runs out of time
- then: the script reports a problem, also where the statement wants the check
  to fail
- source: inferred: my own. A missing command would otherwise count as the
  failure that a `refuted` statement, or a `changes` check at the base, asks for
- check: `python3 -m unittest tests.test_intent_check.Running.test_a_check_that_cannot_run_shows_nothing_either_way tests.test_intent_check.Running.test_a_check_that_runs_out_of_time_is_stopped`

## S8 The working tree is as it was after any run
- kind: changes
- state: checked
- given: a working tree with files edited, added, deleted, made executable and
  linked, and files git ignores; and a run with `--base` that passes, fails, is
  terminated or is killed
- then: every file has its content and mode back, at the end of the run, or
  for a killed run at the start of the next; and no folder that holds ignored
  files is deleted
- source: inferred: my own. The script changes files that may hold work nobody
  has committed
- check: `python3 -m unittest tests.test_intent_check.WorkingTree`

## S9 The script runs where the checks run
- kind: assumes
- state: open
- given: the machine the script runs on
- then: it is Linux or macOS, with git and Python 3.9 or later
- source: inferred: my own
- because: The tests ran on Linux with Python 3.13. The source parses as
  Python 3.9, and this repository's CI is set to run the tests on 3.9. Nothing
  ran on macOS, and Windows is not supported.

## S10 Whoever runs the script would run the change's tests too
- kind: assumes
- state: open
- given: an intent file from a pull request
- then: its check commands are no more dangerous to run than its tests
- source: inferred: my own
- because: Nothing checks it. The script runs the commands as written, so on
  pull requests from outside it needs the care that running their tests needs.

## S11 The report says whether the statements came before the code
- kind: changes
- state: checked
- given: `--base`, and an intent file committed since the base
- then: the report says whether the statements were first committed before
  the code, and names each statement whose kind, given, then or source changed
  since
- source: inferred: the Lean session's answer, "The statement is fixed before
  the proof", and two trial agents' notes that nothing showed the order but
  their word
- check: `python3 -m unittest tests.test_intent_check.History`

## S12 A finding says how its input arrives
- kind: changes
- state: checked
- given: a statement called `refuted`
- then: the script reports a problem unless `arrives` says how the input gets
  there
- source: inferred: the Lean session's answer, "The input can arrive: this
  passes every bar once the producer's code is shown", and a trial reviewer's
  note that the format had no place for it
- check: `python3 -m unittest tests.test_intent_check.States.test_each_state_carries_its_evidence`

## S13 An agent that lists a skill's folder does not find what a case expects
- kind: changes
- state: checked
- given: the test cases of the two skills
- then: none is inside a skill's folder
- source: inferred: two trial agents reported seeing a case's expected
  outcome, or its graders' names, while looking for the skill's files
- check: `python3 -m unittest tests.test_plugin.Plugin.test_no_test_case_sits_inside_a_skill_folder`
