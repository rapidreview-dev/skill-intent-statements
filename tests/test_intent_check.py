"""Tests of intent_check.py, the script that checks an intent file.

Each test builds a small git repository: a `charge` function, a base commit, a
change on top of it, and checks that are one-line Python scripts.

    python3 -m unittest discover -s tests
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "skills" / "intent" / "scripts" / "intent_check.py"
spec = importlib.util.spec_from_file_location("intent_check", SCRIPT)
intent_check = importlib.util.module_from_spec(spec)
sys.modules["intent_check"] = intent_check
spec.loader.exec_module(intent_check)

REQUEST = "Credits must never go negative. A charge that would overdraw is refused."

BASE = "def charge(balance, amount):\n    return balance - amount\n"
# The change refuses an overdraw, and by `>=` also a charge of the whole balance.
HEAD = "def charge(balance, amount):\n    if amount >= balance:\n        return balance\n    return balance - amount\n"

CHECKS = {
    "takes": "assert charge(10, 3) == 7",  # holds before and after
    "refuses": "assert charge(5, 9) == 5",  # holds only with the change
    "whole": "assert charge(5, 5) == 0",  # held before, broken by the change
    "negative": "assert charge(5, -1) == 5",  # fails before and after
    "vacuous": "assert True",
}


def check(name):
    return f"PYTHONPATH=. {sys.executable} checks/{name}.py"


def statement(id="S1", title="A statement", kind="changes", state="checked", given="any balance",
              then="something holds", source='request: "A charge that would overdraw is refused"', **more):
    lines = [f"## {id} {title}", f"- kind: {kind}", f"- state: {state}", f"- given: {given}",
             f"- then: {then}", f"- source: {source}"]
    lines += [f"- {key}: {value}" for key, value in more.items()]
    return "\n".join(lines)


def document(*statements, request=REQUEST, tests="checks/", title="Refuse an overdraw"):
    head = [f"# Intent: {title}", ""]
    if request:
        head += [f"> {request}", ""]
    if tests:
        head += [f"- tests: {tests}", ""]
    return "\n".join(head) + "\n\n".join(statements) + "\n"


class Repository(unittest.TestCase):
    """A repository with a base commit and an uncommitted change on top."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="intent-check-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")
        self.git("config", "commit.gpgsign", "false")
        self.write("calc.py", BASE)
        self.write("README.md", "The balance never goes below zero.\nSecond line.\n")
        self.write(".gitignore", "__pycache__/\nbuild/\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        # The change: the code, and the checks beside it.
        self.write("calc.py", HEAD)
        for name, body in CHECKS.items():
            self.write(f"checks/{name}.py", f"from calc import charge\n{body}\n")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, text=True).stdout

    def write(self, path, text):
        full = self.root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(text)
        return full

    def run_check(self, text, *args, name="intent/overdraw.md"):
        """Run the script over an intent file. Returns (exit status, stdout, stderr)."""
        self.write(name, text)
        out, err = io.StringIO(), io.StringIO()
        before = os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                status = intent_check.main([name, *args])
        finally:
            os.chdir(before)
        return status, out.getvalue(), err.getvalue()

    def snapshot(self):
        """Every file of the working tree: its content, mode and link target.

        Left out are .git, the intent file a test writes, and Python's caches.
        """
        found = {}
        for full in sorted(self.root.rglob("*")):
            relative = full.relative_to(self.root).as_posix()
            if relative.startswith((".git/", "intent/")) or relative == ".git" or "__pycache__" in relative:
                continue
            if full.is_symlink():
                found[relative] = ("link", os.readlink(full))
            elif full.is_file():
                found[relative] = ("file", full.read_bytes(), full.stat().st_mode & 0o777)
        return found


class Reading(Repository):
    def test_reads_the_title_the_request_and_each_statement(self):
        text = document(statement(check=f"`{check('refuses')}`"), statement(id="S2", kind="keeps", check=check("takes")))
        intent = intent_check.parse("x.md", text)
        self.assertEqual(intent.title, "Refuse an overdraw")
        self.assertEqual(intent.request, REQUEST)
        self.assertEqual(intent.tests, ["checks/"])
        self.assertEqual([s.id for s in intent.statements], ["S1", "S2"])
        self.assertEqual(intent.statements[0].get("kind"), "changes")
        self.assertEqual(intent.problems, [])

    def test_a_valid_file_passes_without_running_anything(self):
        status, out, _ = self.run_check(document(statement(check=check("refuses"))))
        self.assertEqual(status, 0, out)
        self.assertIn("check not run", out)
        self.assertIn("1 statement: 1 checked, 0 refuted, 0 open", out)

    def test_bold_keys_and_continued_lines_are_read(self):
        text = "# Intent: T\n\n> " + REQUEST + "\n\n## S1 Refused\n- **kind:** changes\n- **state**: open\n" \
               "- given: a balance\n  and an amount above it\n- then: refused\n- source: inferred, from the name\n- because: no runner here\n"
        intent = intent_check.parse("x.md", text)
        intent_check.validate(intent, self.root)
        self.assertEqual(intent.problems, [])
        self.assertEqual(intent.statements[0].get("given"), "a balance and an amount above it")
        self.assertEqual(intent.statements[0].get("state"), "open")

    def test_a_request_over_several_lines_is_joined(self):
        text = "# Intent: T\n\n> Credits must never\n> go negative.\n\n" + statement(source='request: "never go negative"', state="open", because="x")
        intent = intent_check.parse("x.md", text)
        intent_check.validate(intent, self.root)
        self.assertEqual(intent.request, "Credits must never go negative.")
        self.assertEqual(intent.problems, [])

    def test_what_is_missing_is_named(self):
        cases = {
            "no title": ("> r\n\n" + statement(state="open", because="x", source="inferred: y"), "has no title"),
            "no request": (document(statement(state="open", because="x", source="inferred: y"), request=""), "request is missing"),
            "no statement": (document(), "There is no statement"),
            "heading": (document("## Notes\ntext"), "is not a statement"),
            "unknown field": (document(statement(check="true", chek="true")), 'no field "chek"'),
            "twice": (document(statement(check="true"), statement(check="true")), "S1 is used twice"),
            "kind": (document(statement(kind="adds", check="true")), '"kind" is one of'),
            "state": (document(statement(state="proved", check="true")), '"state" is one of'),
            "given": (document(statement(given="", check="true")), '"given" is missing'),
        }
        for name, (text, wanted) in cases.items():
            with self.subTest(name):
                status, out, _ = self.run_check(text)
                self.assertEqual(status, 1, out)
                self.assertIn(wanted, out)


class States(Repository):
    def test_each_state_carries_its_evidence(self):
        cases = {
            "checked": (statement(), 'called checked needs a "check"'),
            "refuted, no check": (statement(state="refuted", observed="it goes negative", arrives="any caller"), 'called refuted needs a "check"'),
            "refuted, nothing observed": (statement(state="refuted", check="false", arrives="any caller"), 'in "observed"'),
            "refuted, input not traced": (statement(state="refuted", check="false", observed="it goes negative"), 'in "arrives" how its input gets there'),
            "open": (statement(state="open"), 'in "because"'),
        }
        for name, (text, wanted) in cases.items():
            with self.subTest(name):
                status, out, _ = self.run_check(document(text))
                self.assertEqual(status, 1, out)
                self.assertIn(wanted, out)

    def test_open_and_inferred_statements_are_listed(self):
        text = document(
            statement(check=check("refuses")),
            statement(id="S2", kind="assumes", state="open", source="inferred: only billReview calls it", because="nothing checks it at the route"),
        )
        status, out, _ = self.run_check(text)
        self.assertEqual(status, 0, out)
        self.assertIn("Open, assumed and not checked: S2", out)
        self.assertIn("Inferred, asked for by nobody, for a person to confirm: S2", out)
        self.assertIn("Sources: 1 request, 0 existing, 1 inferred", out)


class Sources(Repository):
    def sourced(self, source, *args):
        return self.run_check(document(statement(source=source, state="open", because="x")), *args)

    def test_a_quote_must_be_in_the_request(self):
        status, out, _ = self.sourced('request: "balances are capped at 100"')
        self.assertEqual(status, 1)
        self.assertIn('the request does not say "balances are capped at 100"', out)

    def test_a_quote_is_found_whatever_its_case_spacing_and_quote_marks(self):
        status, out, _ = self.sourced("request: “a charge  that would OVERDRAW is refused”")
        self.assertEqual(status, 0, out)

    def test_a_request_source_quotes_something(self):
        status, out, _ = self.sourced("request: it says so")
        self.assertEqual(status, 1)
        self.assertIn("quotes the words it rests on", out)

    def test_an_existing_source_names_a_file_that_is_there(self):
        self.assertEqual(self.sourced("existing: README.md:1, the rule")[0], 0)
        self.assertEqual(self.sourced("existing: https://example.com/spec the rule")[0], 0)
        status, out, _ = self.sourced("existing: docs/rules.md")
        self.assertEqual(status, 1)
        self.assertIn("docs/rules.md, which is not a file here", out)
        status, out, _ = self.sourced("existing: README.md:40")
        self.assertEqual(status, 1)
        self.assertIn("line 40 of README.md, which is shorter", out)

    def test_an_existing_source_the_change_wrote_is_refused_against_the_base(self):
        self.write("docs/new.md", "A rule the change itself wrote.\n")
        text = document(statement(source="existing: docs/new.md", state="open", because="x"))
        self.assertEqual(self.run_check(text)[0], 0)
        status, out, _ = self.run_check(text, "--base", "HEAD")
        self.assertEqual(status, 1)
        self.assertIn("docs/new.md, is not in the base", out)

    def test_with_a_base_an_existing_source_is_read_there(self):
        # The change rewrites the file: line 2 of the base is the old code.
        self.write("calc.py", "def charge(balance, amount): return balance if amount > balance else balance - amount\n")
        text = document(statement(kind="keeps", source="existing: calc.py:2, the subtraction", state="open", because="x"))
        status, out, _ = self.run_check(text)
        self.assertEqual(status, 1)
        self.assertIn("line 2 of calc.py, which is shorter.", out)
        self.assertEqual(self.run_check(text, "--base", "HEAD")[0], 0)
        status, out, _ = self.run_check(text.replace("calc.py:2", "calc.py:9"), "--base", "HEAD")
        self.assertEqual(status, 1)
        self.assertIn("line 9 of calc.py, which is shorter at the base.", out)

    def test_an_author_source_names_what_the_change_itself_states(self):
        self.write("docs/new.md", "A rule the change itself wrote.\n")
        text = document(statement(source="author: docs/new.md:1", state="open", because="x"))
        status, out, _ = self.run_check(text, "--base", "HEAD")
        self.assertEqual(status, 0, out)
        self.assertIn("Sources: 0 request, 0 existing, 1 author, 0 inferred", out)
        status, out, _ = self.run_check(text.replace("docs/new.md:1", "docs/none.md"), "--base", "HEAD")
        self.assertEqual(status, 1)
        self.assertIn("docs/none.md, which is not a file here", out)

    def test_an_inferred_source_says_from_what(self):
        self.assertEqual(self.sourced("inferred")[0], 1)
        self.assertEqual(self.sourced("inferred: from the function's name")[0], 0)
        status, out, _ = self.sourced("the code")
        self.assertEqual(status, 1)
        self.assertIn('"source" starts with one of request, existing, author, inferred', out)


class Running(Repository):
    def test_a_checked_statement_must_pass(self):
        status, out, _ = self.run_check(document(statement(check=check("refuses"))), "--run")
        self.assertEqual(status, 0, out)
        self.assertIn("holds with the change", out)
        status, out, _ = self.run_check(document(statement(check=check("negative"))), "--run")
        self.assertEqual(status, 1)
        self.assertIn("S1: it is called checked, and its check fails (exit 1)", out)
        self.assertIn("AssertionError", out)  # the output of an unexpected result is shown

    def test_a_refuted_statement_must_fail(self):
        refuted = dict(state="refuted", observed="the balance rises to 6", arrives="refund passes a negative amount")
        status, out, _ = self.run_check(document(statement(check=check("negative"), **refuted)), "--run")
        self.assertEqual(status, 0, out)
        self.assertIn("Refuted, shown not to hold: S1", out)
        status, out, _ = self.run_check(document(statement(check=check("takes"), **refuted)), "--run")
        self.assertEqual(status, 1)
        self.assertIn("it is called refuted, and its check passes", out)

    def test_a_check_that_cannot_run_shows_nothing_either_way(self):
        for state in (dict(state="checked"), dict(state="refuted", observed="x", arrives="y")):
            with self.subTest(state["state"]):
                status, out, _ = self.run_check(document(statement(check="no-such-command-here", **state)), "--run")
                self.assertEqual(status, 1)
                self.assertIn("could not be run (exit 127)", out)

    def test_a_check_that_runs_out_of_time_is_stopped(self):
        status, out, _ = self.run_check(document(statement(check="sleep 30")), "--run", "--timeout", "0.3")
        self.assertEqual(status, 1)
        self.assertIn("ran out of time", out)

    def test_an_open_statement_is_not_run(self):
        text = document(statement(state="open", because="needs a database", check="exit 1"))
        status, out, _ = self.run_check(text, "--run")
        self.assertEqual(status, 0, out)
        self.assertIn("not checked: needs a database", out)

    def test_checks_run_from_the_repository_root(self):
        (self.root / "deep").mkdir()
        self.write("intent/overdraw.md", document(statement(check="test -f calc.py")))
        result = subprocess.run([sys.executable, str(SCRIPT), "../intent/overdraw.md", "--run"],
                                cwd=self.root / "deep", capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_missing_file_is_exit_2(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "intent/none.md"], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("intent/none.md", result.stderr)


class WithoutTheChange(Repository):
    def test_a_check_of_new_behaviour_must_fail_without_the_change(self):
        status, out, _ = self.run_check(document(statement(check=check("refuses"))), "--base", "HEAD")
        self.assertEqual(status, 0, out)
        self.assertIn("holds with the change, fails without it", out)

    def test_a_check_that_passes_without_the_change_shows_nothing(self):
        for name in ("vacuous", "takes"):
            with self.subTest(name):
                status, out, _ = self.run_check(document(statement(check=check(name))), "--base", "HEAD")
                self.assertEqual(status, 1)
                self.assertIn("its check passes with the change taken out", out)

    def test_kept_behaviour_must_hold_before_and_after(self):
        status, out, _ = self.run_check(document(statement(kind="keeps", check=check("takes"))), "--base", "HEAD")
        self.assertEqual(status, 0, out)
        self.assertIn("holds with the change, holds without it", out)
        status, out, _ = self.run_check(document(statement(kind="keeps", check=check("refuses"))), "--base", "HEAD")
        self.assertEqual(status, 1)
        self.assertIn("called kept, and its check fails with the change taken out", out)

    def test_a_regression_held_before_and_fails_now(self):
        refuted = dict(kind="keeps", state="refuted", observed="a charge of the whole balance is refused",
                       arrives="not shown: no caller is in this repository")
        status, out, _ = self.run_check(document(statement(id="F1", check=check("whole"), **refuted)), "--base", "HEAD")
        self.assertEqual(status, 0, out)
        self.assertIn("fails with the change, holds without it", out)
        status, out, _ = self.run_check(document(statement(id="F1", check=check("negative"), **refuted)), "--base", "HEAD")
        self.assertEqual(status, 1)
        self.assertIn("called a regression, and its check fails with the change taken out too", out)

    def test_the_header_must_say_which_files_hold_the_checks(self):
        status, out, _ = self.run_check(document(statement(check=check("refuses")), tests=""), "--base", "HEAD")
        self.assertEqual(status, 1)
        self.assertIn("the header names the files that hold the checks", out)

    def test_the_base_is_where_the_branch_left_it(self):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "the change")
        status, out, _ = self.run_check(document(statement(check=check("refuses"))), "--base", "HEAD~1")
        self.assertEqual(status, 0, out)
        self.assertIn("fails without it", out)

    def test_no_git_repository_is_exit_2(self):
        folder = Path(tempfile.mkdtemp(prefix="intent-check-plain-"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        (folder / "i.md").write_text(document(statement(check="true")))
        env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(folder.parent))
        run = lambda *args: subprocess.run([sys.executable, str(SCRIPT), "i.md", *args], cwd=folder, env=env, capture_output=True, text=True)
        self.assertEqual(run("--run").returncode, 0)
        result = run("--base", "HEAD")
        self.assertEqual(result.returncode, 2)
        self.assertIn("needs a git repository", result.stderr)


class WorkingTree(Repository):
    """Taking the change out and putting it back leaves every file as it was."""

    def setUp(self):
        super().setUp()
        # A change of every kind: a file edited, added, deleted, made
        # executable, a link, and a folder the change added.
        self.write("tool.sh", "#!/bin/sh\necho base\n")
        self.write("old.txt", "deleted by the change\n")
        self.git("add", "tool.sh", "old.txt")
        self.git("commit", "-q", "-m", "more base")
        self.write("tool.sh", "#!/bin/sh\necho head\n").chmod(0o755)
        (self.root / "old.txt").unlink()
        self.write("pkg/new/module.py", "VALUE = 1\n")
        os.symlink("calc.py", self.root / "link.py")
        self.write("build/output.bin", "ignored by git, and not to be lost\n")

    def test_the_tree_is_put_back_after_a_passing_and_a_failing_run(self):
        before = self.snapshot()
        for name, wanted in (("refuses", 0), ("vacuous", 1)):
            with self.subTest(name):
                status, out, _ = self.run_check(document(statement(check=check(name))), "--base", "HEAD")
                self.assertEqual(status, wanted, out)
                self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.root / ".git" / "intent-check").exists())

    def test_the_change_really_is_out_while_the_base_checks_run(self):
        probe = ("test ! -e pkg && test ! -e link.py && test -f old.txt && grep -q base tool.sh && test ! -x tool.sh"
                 " && test -f checks/takes.py && test -f intent/overdraw.md && test -f build/output.bin")
        # `keeps` wants the check to hold with the change too, so run one that
        # holds there and the probe only where the change is out.
        text = document(
            statement(kind="keeps", check=f"if grep -q head tool.sh; then true; else {probe}; fi"),
        )
        status, out, _ = self.run_check(text, "--base", "HEAD")
        self.assertEqual(status, 0, out)

    def test_a_run_that_was_killed_is_put_back_by_the_next_one(self):
        before = self.snapshot()
        base = self.git("rev-parse", "HEAD").strip()
        taken = intent_check.TakenOut(self.root, base, lambda path: path.startswith("checks/"))
        taken.__enter__()  # and never leaves: the process is gone
        self.assertNotEqual(self.snapshot(), before)
        manifest = self.root / ".git" / "intent-check" / "manifest.json"
        manifest.write_text(json.dumps(dict(json.loads(manifest.read_text()), pid=2 ** 22 + 12345)))
        status, _, err = self.run_check(document(statement(check=check("refuses"))), "--run")
        self.assertEqual(status, 0)
        self.assertIn("An earlier run was cut off", err)
        self.assertEqual(self.snapshot(), before)

    def test_leftover_copies_without_their_list_are_only_cleared(self):
        # A run cut off before it changed anything, or after it had put everything back.
        before = self.snapshot()
        leftover = self.root / ".git" / "intent-check" / "files"
        leftover.mkdir(parents=True)
        (leftover / "0").write_text("a copy of something")
        status, _, _ = self.run_check(document(statement(check=check("refuses"))), "--run")
        self.assertEqual(status, 0)
        self.assertFalse(leftover.parent.exists())
        self.assertEqual(self.snapshot(), before)

    def test_a_change_of_the_same_size_made_this_second_is_not_served_from_a_cache(self):
        # Python caches bytecode by the source's time in seconds and its size.
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "the change so far")
        self.write("sign.py", "def step(n):\n    return n - 1\n")
        self.git("add", "sign.py")
        self.git("commit", "-q", "-m", "base")
        steps_up = f"{sys.executable} -c 'from sign import step; assert step(5) == 6'"
        for attempt in range(3):
            with self.subTest(attempt=attempt):
                self.write("sign.py", "def step(n):\n    return n + 1\n")
                status, out, _ = self.run_check(document(statement(check=steps_up)), "--base", "HEAD")
                self.assertEqual(status, 0, out)  # the base run saw the base, not the cached change
                after = subprocess.run(steps_up, shell=True, cwd=self.root, capture_output=True, text=True)
                self.assertEqual(after.returncode, 0, after.stderr)  # and afterwards the change is back
                self.git("checkout", "--", "sign.py")

    def test_a_folder_that_holds_ignored_files_is_never_deleted(self):
        # The base has a file where the change has a folder with ignored files.
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "the change so far")
        self.write("cache", "a file at the base\n")
        self.git("add", "cache")
        self.git("commit", "-q", "-m", "base with a file")
        base = self.git("rev-parse", "HEAD").strip()
        (self.root / "cache").unlink()
        self.write("cache/tracked.txt", "added by the change\n")
        self.write("cache/__pycache__/x.pyc", "ignored\n")
        before = self.snapshot()
        with intent_check.TakenOut(self.root, base, lambda path: False) as taken:
            self.assertTrue((self.root / "cache" / "__pycache__" / "x.pyc").is_file())
            self.assertIn("cache", taken.skipped)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue((self.root / "cache" / "__pycache__" / "x.pyc").is_file())

    def test_an_interrupted_run_puts_the_tree_back(self):
        before = self.snapshot()
        self.write("intent/overdraw.md", document(statement(kind="keeps", check="if grep -q head tool.sh; then true; else sleep 30; fi")))
        process = subprocess.Popen([sys.executable, str(SCRIPT), "intent/overdraw.md", "--base", "HEAD"],
                                   cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: (process.kill(), process.communicate()))
        journal = self.root / ".git" / "intent-check" / "manifest.json"

        def change_is_out():
            try:  # the script may be replacing the file at this very moment
                return journal.exists() and "base" in (self.root / "tool.sh").read_text()
            except OSError:
                return False

        for _ in range(400):  # until the change is out
            if change_is_out():
                break
            time.sleep(0.05)
        self.assertTrue(change_is_out())
        process.terminate()
        _, err = process.communicate(timeout=20)
        self.assertEqual(process.returncode, 2, err)
        self.assertIn("The working tree is as it was", err)
        self.assertEqual(self.snapshot(), before)


class History(Repository):
    """Whether git shows that the statements came before the code."""

    def commit(self, message, *paths):
        self.git("add", *paths)
        self.git("commit", "-q", "-m", message)

    def setUp(self):
        super().setUp()
        self.git("stash", "-q", "--include-untracked")  # start from the base, the change set aside
        self.text = document(statement(check=check("refuses"), then="the charge is refused"))

    def test_statements_committed_on_their_own_and_left_alone(self):
        self.write("intent/overdraw.md", self.text)
        self.commit("the statements", "intent")
        self.git("stash", "pop", "-q")
        self.commit("the checks and the code", "-A")
        status, out, _ = self.run_check(self.text, "--base", "HEAD~2")
        self.assertEqual(status, 0, out)
        self.assertRegex(out, r"note: The statements were first committed in [0-9a-f]{7}, on their own, before the code\. "
                              r"Since then: no statement changed in what it says\.")

    def test_a_statement_reworded_after_the_code_is_named(self):
        self.write("intent/overdraw.md", self.text)
        self.write("checks/placeholder.py", "")
        self.commit("the statements and their checks", "intent", "checks")
        self.git("stash", "pop", "-q")
        later = document(
            statement(check=check("refuses"), then="the charge is refused, or taken when that is easier"),
            statement(id="S2", kind="keeps", check=check("takes")),
        )
        status, out, _ = self.run_check(later, "--base", "HEAD~1", "--format", "json")
        self.assertEqual(status, 0, out)
        (report,) = json.loads(out)
        self.assertTrue(report["history"]["before_the_code"])
        self.assertEqual(report["history"]["changed"], {"S1": ["then"]})
        self.assertEqual(report["history"]["added"], ["S2"])
        self.assertIn("with their checks, before the code. Since then: changed S1 (then); added S2.", report["notes"][0])

    def test_evidence_added_later_is_not_a_changed_statement(self):
        first = document(statement(state="open", because="its check is not written yet"))
        self.write("intent/overdraw.md", first)
        self.commit("the statements", "intent")
        self.git("stash", "pop", "-q")
        status, out, _ = self.run_check(document(statement(check=check("refuses"), note="seen while probing")), "--base", "HEAD~1")
        self.assertEqual(status, 0, out)
        self.assertIn("Since then: no statement changed in what it says.", out)

    def test_statements_committed_with_the_code_show_nothing(self):
        self.git("stash", "pop", "-q")
        self.write("intent/overdraw.md", self.text)
        self.commit("everything at once", "-A")
        status, out, _ = self.run_check(self.text, "--base", "HEAD~1", "--format", "markdown")
        self.assertEqual(status, 0, out)
        self.assertRegex(out, r"- The statements were first committed in [0-9a-f]{7} together with 1 other file, "
                              r"so the history does not show that they came before the code\.")

    def test_statements_not_committed_show_nothing(self):
        self.git("stash", "pop", "-q")
        status, out, _ = self.run_check(self.text, "--base", "HEAD")
        self.assertEqual(status, 0, out)
        self.assertIn("The statements are not committed, so the history cannot show that they came before the code.", out)


class Globs(unittest.TestCase):
    def test_the_patterns_of_the_tests_header(self):
        cases = [
            ("checks/", "checks/a.py", True),
            ("checks/", "checks/deep/a.py", True),
            ("checks/", "src/checks.py", False),
            ("*.test.ts", "src/deep/a.test.ts", True),
            ("*.test.ts", "src/a.ts", False),
            ("tests/**", "tests/unit/a.py", True),
            ("**/*_test.go", "pkg/a_test.go", True),
            ("**/*_test.go", "a_test.go", True),
            ("src/*.py", "src/deep/a.py", False),
            ("vitest.config.ts", "vitest.config.ts", True),
        ]
        for pattern, path, wanted in cases:
            with self.subTest(pattern=pattern, path=path):
                self.assertEqual(bool(intent_check.glob_regex(pattern).match(path)), wanted)


class Reports(Repository):
    TEXT = document(
        statement(title="An overdraw is refused", check=check("refuses")),
        statement(id="S2", title="Amounts | whole numbers", kind="assumes", state="open",
                  source="inferred: the callers pass constants", because="nothing checks it"),
    )

    def test_the_markdown_report_is_a_table_with_the_open_and_inferred_named(self):
        status, out, _ = self.run_check(self.TEXT, "--base", "HEAD", "--format", "markdown")
        self.assertEqual(status, 0, out)
        self.assertIn("| S1 | An overdraw is refused | changes | checked | holds with the change, fails without it |", out)
        self.assertIn("| S2 | Amounts \\| whole numbers | assumes | **open** | not checked |", out)
        self.assertIn("- **Open, assumed and not checked:**\n  - **S2:** nothing checks it", out)
        self.assertIn("- **Inferred, asked for by nobody, for a person to confirm:** S2", out)

    def test_the_json_report_carries_each_run(self):
        status, out, _ = self.run_check(self.TEXT, "--base", "HEAD", "--format", "json")
        self.assertEqual(status, 0, out)
        (report,) = json.loads(out)
        self.assertEqual(report["counts"]["checked"], 1)
        first = report["statements"][0]
        self.assertEqual(first["runs"]["with"]["outcome"], "holds")
        self.assertEqual(first["runs"]["without"]["outcome"], "fails")
        self.assertEqual(report["statements"][1]["source_from"], "inferred")


if __name__ == "__main__":
    unittest.main()
