#!/usr/bin/env python3
"""intent_check: check an intent file, and run the checks it names.

Whoever wrote the intent file, a person or a model, is not trusted. This script
is the small part that is. It uses no model and nothing outside Python's
standard library (3.9 or later), and it does three things:

1. It reads the statements and reports what is malformed: a statement with no
   source, a quote the request does not hold, a state without its evidence.
2. With --run, it runs each statement's check at the working tree. A statement
   called `checked` must pass, and one called `refuted` must fail.
3. With --base REF, it also runs checks with the change taken out: every file
   that differs from the base is put back as it was there, except the files
   that hold the checks. A check for behaviour the change brings (`changes`)
   must fail then, and one for behaviour it keeps (`keeps`) must pass. The
   working tree is put back afterwards, also when the run is interrupted.

It exits 0 when everything is as stated, 1 when something is not, and 2 when
it could not do the job (a missing file, no git repository, a bad base).

The format is described in ../references/format.md.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

KINDS = ("changes", "keeps", "assumes")
STATES = ("checked", "refuted", "open")
SOURCES = ("request", "existing", "author", "inferred")
FIELDS = ("kind", "state", "given", "then", "source", "check", "observed", "arrives", "because", "note")
# What a statement says, as against the evidence for it. A change to one of
# these after the statement was first committed is a changed statement.
SAID = ("kind", "given", "then", "source")
HEADER_FIELDS = ("tests",)

TITLE = re.compile(r"^#\s+Intent:\s*(.+?)\s*$")
HEADING = re.compile(r"^##\s+(.*?)\s*$")
STATEMENT_HEADING = re.compile(r"^([A-Za-z]+\d+)[:.)]?\s+(.+)$")
# "- kind: changes"; the key may be bold, as in "- **kind:** changes".
FIELD = re.compile(r"^[-*]\s+\**([A-Za-z][A-Za-z-]*)\**:\**\s*(.*)$")
SOURCE = re.compile(r"^(\w+)\s*[:,\u2014\u2013-]?\s*(.*)$", re.S)
QUOTED = re.compile(r'"([^"]+)"')

# Exit statuses a shell gives when it could not run the command at all. They
# never count as a check failing: a check that cannot run shows nothing.
COULD_NOT_RUN = (126, 127)


class Unusable(Exception):
    """The job cannot be done at all (exit 2), as against a problem found (exit 1)."""


@dataclass
class Statement:
    id: str
    title: str
    line: int
    fields: dict = field(default_factory=dict)
    source_from: str = ""
    source_text: str = ""
    runs: dict = field(default_factory=dict)  # "with" / "without" the change -> a run

    def get(self, key: str) -> str:
        return self.fields.get(key, "")


@dataclass
class Intent:
    path: str
    title: str = ""
    request: str = ""
    tests: list = field(default_factory=list)
    statements: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    history: dict = field(default_factory=dict)


# ---------------------------------------------------------------- reading


def normalize(text: str) -> str:
    """Text as compared for a quote: case, spacing and typographic quotes aside."""
    for curly, straight in (("\u201c", '"'), ("\u201d", '"'), ("\u2018", "'"), ("\u2019", "'")):
        text = text.replace(curly, straight)
    return re.sub(r"\s+", " ", text).strip().lower()


def strip_code(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        value = value.strip("`").strip()
    return value


def parse(path: str, text: str) -> Intent:
    intent = Intent(path=path)
    request_lines = []
    current = None  # the statement being read, or None in the header
    last_key = None  # the field a continuation line belongs to
    header = {}

    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        title = TITLE.match(line)
        if title and not intent.title and current is None:
            intent.title = title.group(1)
            last_key = None
            continue
        heading = HEADING.match(line)
        if heading:
            last_key = None
            statement = STATEMENT_HEADING.match(heading.group(1))
            if not statement:
                intent.problems.append(
                    f"line {number}: the heading \"{heading.group(1)}\" is not a statement. "
                    "A statement's heading is an id and a title, such as \"## S1 A full cart is refused\"."
                )
                current = None
                continue
            current = Statement(id=statement.group(1), title=statement.group(2), line=number)
            if any(other.id == current.id for other in intent.statements):
                intent.problems.append(f"line {number}: the id {current.id} is used twice.")
            intent.statements.append(current)
            continue
        if current is None and line.lstrip().startswith(">"):
            request_lines.append(line.lstrip()[1:].strip())
            last_key = None
            continue
        item = FIELD.match(line)
        if item:
            key, value = item.group(1).lower(), item.group(2).strip()
            target = header if current is None else current.fields
            allowed = HEADER_FIELDS if current is None else FIELDS
            where = "the header" if current is None else current.id
            if key not in allowed:
                intent.problems.append(
                    f"line {number}: {where} has no field \"{key}\". Its fields are: {', '.join(allowed)}."
                )
                last_key = None
                continue
            if key in target:
                intent.problems.append(f"line {number}: {where} gives \"{key}\" twice.")
            target[key] = value
            last_key = (target, key)
            continue
        if last_key and line.startswith((" ", "\t")) and line.strip():
            target, key = last_key
            target[key] = (target[key] + " " + line.strip()).strip()
            continue
        last_key = None

    intent.request = " ".join(part for part in request_lines if part)
    intent.tests = [glob.strip().strip("`") for glob in header.get("tests", "").split(",") if glob.strip()]
    return intent


def validate(intent: Intent, root: Path, base=None) -> None:
    """What code can tell from the file alone, and from the files it names.

    With a base, an existing source is looked up there, not in the working tree.
    """
    problems = intent.problems
    if not intent.title:
        problems.append("The file has no title. Its first line is \"# Intent: <what the change is for>\".")
    if not intent.request:
        problems.append(
            "The request is missing. Quote it word for word in lines that start with \">\", "
            "above the first statement."
        )
    if not intent.statements:
        problems.append("There is no statement.")

    for statement in intent.statements:
        name = statement.id
        kind, state = statement.get("kind"), statement.get("state")
        if kind not in KINDS:
            problems.append(f"{name}: \"kind\" is one of {', '.join(KINDS)}; it is \"{kind}\".")
        if state not in STATES:
            problems.append(f"{name}: \"state\" is one of {', '.join(STATES)}; it is \"{state}\".")
        for key in ("given", "then", "source"):
            if not statement.get(key):
                problems.append(f"{name}: \"{key}\" is missing.")
        statement.fields["check"] = strip_code(statement.get("check"))
        if state in ("checked", "refuted") and not statement.get("check"):
            problems.append(f"{name}: a statement called {state} needs a \"check\", a command that passes only when it holds.")
        if state == "refuted" and not statement.get("observed"):
            problems.append(f"{name}: a refuted statement says what happens instead, in \"observed\".")
        if state == "refuted" and not statement.get("arrives"):
            problems.append(
                f"{name}: a refuted statement says in \"arrives\" how its input gets there: "
                "the line that produces it, or that this was not shown."
            )
        if state == "open" and not statement.get("because"):
            problems.append(f"{name}: an open statement says in \"because\" why it is not checked and what would check it.")
        if statement.get("source"):
            validate_source(intent, statement, root, base)


def validate_source(intent: Intent, statement: Statement, root: Path, base=None) -> None:
    match = SOURCE.match(statement.get("source"))
    origin = match.group(1).lower() if match else ""
    rest = match.group(2).strip() if match else ""
    if origin not in SOURCES:
        intent.problems.append(
            f"{statement.id}: \"source\" starts with one of {', '.join(SOURCES)}, saying where the intent comes from."
        )
        return
    statement.source_from, statement.source_text = origin, rest
    if origin == "request":
        quotes = QUOTED.findall(normalize_quotes(rest))
        if not quotes:
            intent.problems.append(f"{statement.id}: a source in the request quotes the words it rests on, in double quotes.")
        request = normalize(intent.request)
        for quote in quotes:
            if normalize(quote) not in request:
                intent.problems.append(f"{statement.id}: the request does not say \"{quote}\".")
    elif origin in ("existing", "author"):
        anchor = rest.split()[0].strip("`,;") if rest else ""
        if not anchor:
            intent.problems.append(f"{statement.id}: a source called {origin} names a file, as path or path:line, or a URL.")
        elif not re.match(r"^https?://", anchor):
            path, _, line = anchor.partition(":")
            lines, where = None, ""
            if origin == "existing" and base:
                # What was there before the change is what the base holds.
                if base_entry(root, base, path)[1] != "blob":
                    intent.problems.append(
                        f"{statement.id}: its source, {path}, is not in the base. A source the change wrote is "
                        "the change vouching for itself: call it inferred, or quote the request. "
                        "In a review, what the change states is an \"author\" source."
                    )
                else:
                    lines = len(git(root, "show", f"{base}:{path}").splitlines())
                    where = " at the base"
            elif not (root / path).is_file():
                intent.problems.append(f"{statement.id}: its source names {path}, which is not a file here.")
            else:
                lines = count_lines(root / path)
            if lines is not None and line.isdigit() and int(line) > lines:
                intent.problems.append(f"{statement.id}: its source names line {line} of {path}, which is shorter{where}.")
    elif not rest:
        intent.problems.append(f"{statement.id}: an inferred source says what it was inferred from.")


def normalize_quotes(text: str) -> str:
    return text.replace("\u201c", '"').replace("\u201d", '"')


def count_lines(path: Path) -> int:
    try:
        return len(path.read_text(errors="replace").splitlines())
    except OSError:
        return 0


# ------------------------------------------------------------------- git


def git(root: Path, *args: str, binary: bool = False):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if result.returncode != 0:
        raise Unusable(f"git {' '.join(args)}: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout if binary else result.stdout.decode(errors="replace")


def repository_root(start: Path):
    result = subprocess.run(["git", "-C", str(start), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return Path(result.stdout.strip()) if result.returncode == 0 and result.stdout.strip() else None


def glob_regex(pattern: str):
    """A glob as a regex over a path from the repository root.

    `**/` crosses folders, `*` and `?` stay inside one. A pattern that ends in
    `/` covers the folder, and one with no `/` matches the name at any depth,
    as in .gitignore.
    """
    if pattern.endswith("/"):
        pattern += "**"
    elif "/" not in pattern:
        pattern = "**/" + pattern
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def history(intent: Intent, root: Path, base: str, own: str, kept) -> None:
    """What git shows about when the statements were written, as a note.

    The statement is fixed before the proof: the note says whether the history
    shows that, and which statements changed in what they say since they were
    first committed.
    """
    if own.startswith("..") or base_entry(root, base, own)[1] == "blob":
        return  # outside the repository, or older than the change
    commits = git(root, "log", "--reverse", "--format=%H", f"{base}..HEAD", "--", own).split()
    if not commits:
        intent.history = {"committed": False}
        intent.notes.append("The statements are not committed, so the history cannot show that they came before the code.")
        return
    first = commits[0]
    beside = [path for path in git(root, "show", "--name-only", "--format=", first).splitlines() if path and path != own]
    code = [path for path in beside if not kept(path)]
    before = {statement.id: statement for statement in parse(own, git(root, "show", f"{first}:{own}")).statements}
    now = {statement.id: statement for statement in intent.statements}
    changed = {}
    for name in now:
        if name in before:
            keys = [key for key in SAID if normalize(before[name].get(key)) != normalize(now[name].get(key))]
            if keys:
                changed[name] = keys
    added = [name for name in now if name not in before]
    removed = [name for name in before if name not in now]
    intent.history = {
        "committed": True, "first_commit": first, "before_the_code": not code,
        "changed": changed, "added": added, "removed": removed,
    }
    if code:
        note = (f"The statements were first committed in {first[:7]} together with {len(code)} other "
                f"file{'' if len(code) == 1 else 's'}, so the history does not show that they came before the code.")
    else:
        note = f"The statements were first committed in {first[:7]}, {'with their checks' if beside else 'on their own'}, before the code."
    since = []
    if changed:
        since.append("changed " + ", ".join(f"{name} ({', '.join(keys)})" for name, keys in changed.items()))
    if added:
        since.append("added " + ", ".join(added))
    if removed:
        since.append("removed " + ", ".join(removed))
    intent.notes.append(note + " Since then: " + ("; ".join(since) if since else "no statement changed in what it says") + ".")


class TakenOut:
    """The change set aside: the files that differ from the base, as they were there.

    The files to put back are copied into the repository's git folder first,
    with a list of them, and only then is anything changed. A run that is
    killed leaves that folder behind, and the next run puts the files back
    from it before doing anything else.
    """

    def __init__(self, root: Path, base: str, keep):
        self.root, self.base, self.keep = root, base, keep
        self.journal = journal_folder(root)
        self.entries = []
        self.skipped = []

    def __enter__(self):
        restore_leftover(self.root)
        tracked = git(self.root, "diff", "--name-only", "--no-renames", "-z", self.base, "--").split("\0")
        untracked = git(self.root, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
        paths = sorted({path for path in tracked + untracked if path})
        plan = []
        for path in paths:
            if self.keep(path):
                continue
            mode, kind, blob = base_entry(self.root, self.base, path)
            full = self.root / path
            if path.endswith("/") or kind == "commit" or (full.is_dir() and not full.is_symlink() and kind != "blob"):
                self.skipped.append(path.rstrip("/"))  # a submodule or a nested repository
                continue
            plan.append((path, mode, blob if kind == "blob" else None))

        files = self.journal / "files"
        files.mkdir(parents=True)
        for index, (path, _mode, _blob) in enumerate(plan):
            full = self.root / path
            entry = {"path": path, "had": "none"}
            if full.is_symlink():
                entry.update(had="link", target=os.readlink(full))
            elif full.is_file():
                shutil.copy2(full, files / str(index))
                entry.update(had="file", copy=str(index))
            self.entries.append(entry)
        manifest = {"pid": os.getpid(), "entries": self.entries}
        (self.journal / "manifest.json").write_text(json.dumps(manifest))

        try:
            wait_for_a_new_second(self.root, [path for path, _mode, _blob in plan])
            # Deepest first, so a folder the change added is empty by the time
            # its own turn comes.
            for path, _mode, _blob in reversed(plan):
                remove(self.root, self.root / path)
            for path, mode, blob in plan:
                if blob is None:
                    continue
                full = self.root / path
                if full.is_dir() and not full.is_symlink():
                    self.skipped.append(path)  # a folder here still holds files
                    continue
                full.parent.mkdir(parents=True, exist_ok=True)
                content = git(self.root, "cat-file", "blob", blob, binary=True)
                if mode == "120000":
                    os.symlink(content.decode(), full)
                else:
                    # Written now, so the file is newer than anything built from
                    # the version it replaces, and a build that goes by time
                    # rebuilds.
                    full.write_bytes(content)
                    full.chmod(0o755 if mode == "100755" else 0o644)
        except BaseException:
            put_back_for_sure(self.root, self.journal)
            raise
        return self

    def __exit__(self, *exc):
        put_back_for_sure(self.root, self.journal)
        return False


def journal_folder(root: Path) -> Path:
    return Path(git(root, "rev-parse", "--absolute-git-dir").strip()) / "intent-check"


def base_entry(root: Path, base: str, path: str):
    out = git(root, "ls-tree", "-z", base, "--", path.rstrip("/"))
    for record in out.split("\0"):
        if not record:
            continue
        meta, _, name = record.partition("\t")
        if name == path.rstrip("/"):
            mode, kind, blob = meta.split()
            return mode, kind, blob
    return None, None, None


def remove(root: Path, full: Path) -> None:
    """Remove a file or a link, and the folders that leaves empty.

    A folder that still holds something is left alone: what is in it may be
    ignored by git, and then nothing could bring it back.
    """
    if full.is_symlink() or full.is_file():
        full.unlink()
        folder = full.parent
    else:
        folder = full
    while folder != root and folder.is_dir() and not folder.is_symlink():
        try:
            folder.rmdir()
        except OSError:
            break
        folder = folder.parent


def wait_for_a_new_second(root: Path, paths) -> None:
    """Wait until the clock's second is past the newest of these files.

    A cache keyed on a file's time in whole seconds and its size, as Python's
    bytecode cache is, takes a file rewritten within the same second at the
    same size for the one it already compiled. Checks would then run the
    wrong version, and so would whatever runs after this script. The wait is
    under a second, and only when a file was written that recently.
    """
    newest = 0.0
    for path in paths:
        try:
            newest = max(newest, os.lstat(root / path).st_mtime)
        except OSError:
            pass
    while int(time.time()) <= int(newest) and newest - time.time() < 2:
        time.sleep(0.05)


def put_back(root: Path, journal: Path) -> None:
    manifest_path = journal / "manifest.json"
    if manifest_path.is_file():
        entries = json.loads(manifest_path.read_text())["entries"]
        wait_for_a_new_second(root, [entry["path"] for entry in entries])
        for entry in reversed(entries):
            remove(root, root / entry["path"])
        for entry in entries:
            full = root / entry["path"]
            if entry["had"] == "none":
                continue
            full.parent.mkdir(parents=True, exist_ok=True)
            if entry["had"] == "link":
                os.symlink(entry["target"], full)
            else:
                # copy, not copy2: the time is now, for the same reason as above.
                shutil.copy(journal / "files" / entry["copy"], full)
        # The list goes first. Without it the folder is only leftovers, so a
        # run cut off here cannot put back from copies that are half deleted.
        manifest_path.unlink()
    shutil.rmtree(journal, ignore_errors=True)


def put_back_for_sure(root: Path, journal: Path) -> None:
    """Put the files back, and finish even when a second signal arrives meanwhile.

    Putting back can be repeated: it starts from the copies each time.
    """
    while True:
        try:
            put_back(root, journal)
            return
        except KeyboardInterrupt:
            continue


def restore_leftover(root: Path):
    """Put back what an earlier run that was killed left taken out."""
    journal = journal_folder(root)
    if not journal.exists():
        return None
    manifest_path = journal / "manifest.json"
    if manifest_path.is_file():
        pid = json.loads(manifest_path.read_text()).get("pid")
        if pid and pid != os.getpid() and still_running(pid):
            raise Unusable(f"another intent_check (process {pid}) has the change taken out of this working tree. Wait for it.")
        put_back(root, journal)
        return "An earlier run was cut off with the change taken out. The working tree is put back as it was."
    shutil.rmtree(journal, ignore_errors=True)
    return None


def still_running(pid: int) -> bool:
    """Whether that process is an intent_check, and not another that got its id."""
    try:
        result = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True)
    except OSError:
        return False
    return result.returncode == 0 and "intent_check" in result.stdout


# --------------------------------------------------------------- running


def run_check(command: str, root: Path, timeout: float) -> dict:
    # CI=true keeps test runners from watching for changes and from writing
    # snapshots that are missing, which would make a check pass by itself.
    env = dict(os.environ, CI=os.environ.get("CI", "true"))
    started = time.monotonic()
    process = subprocess.Popen(
        command, shell=True, cwd=str(root), env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
    )
    timed_out = False
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        kill_group(process)
        output, _ = process.communicate()
    except BaseException:
        kill_group(process)  # interrupted: the check does not outlive the run
        process.communicate()
        raise
    lines = output.decode(errors="replace").splitlines()
    return {
        "exit": None if timed_out else process.returncode,
        "timed_out": timed_out,
        "seconds": round(time.monotonic() - started, 1),
        "tail": lines[-25:],
    }


def kill_group(process) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, AttributeError):
        process.kill()


def outcome(run: dict) -> str:
    if run["timed_out"] or run["exit"] in COULD_NOT_RUN:
        return "could not run"
    return "holds" if run["exit"] == 0 else "fails"


def wanted_with(statement: Statement):
    return {"checked": "holds", "refuted": "fails"}.get(statement.get("state"))


def wanted_without(statement: Statement):
    kind, state = statement.get("kind"), statement.get("state")
    if state == "checked" and kind == "changes":
        return "fails"
    if kind == "keeps" and state in ("checked", "refuted"):
        return "holds"
    return None


def run_all(intent: Intent, root: Path, phase: str, wanted, timeout: float, cache: dict) -> None:
    for statement in intent.statements:
        command, want = statement.get("check"), wanted(statement)
        if not command or want is None:
            continue
        if (phase, command) not in cache:
            cache[(phase, command)] = run_check(command, root, timeout)
        run = dict(cache[(phase, command)], wanted=want)
        run["outcome"] = outcome(run)
        statement.runs[phase] = run
        if run["outcome"] != want:
            intent.problems.append(explain(statement, phase, run))


def explain(statement: Statement, phase: str, run: dict) -> str:
    name, state, kind = statement.id, statement.get("state"), statement.get("kind")
    if run["outcome"] == "could not run":
        why = "ran out of time" if run["timed_out"] else f"could not be run (exit {run['exit']})"
        place = "" if phase == "with" else " with the change taken out"
        return f"{name}: its check {why}{place}, so it shows nothing: {statement.get('check')}"
    if phase == "with":
        if state == "checked":
            return f"{name}: it is called checked, and its check fails (exit {run['exit']})."
        return f"{name}: it is called refuted, and its check passes: nothing shows the statement broken."
    if state == "checked" and kind == "changes":
        return (
            f"{name}: its check passes with the change taken out, so it does not show what the change does. "
            "Make the check depend on the change, or call the statement \"keeps\"."
        )
    if state == "checked":
        return f"{name}: it is called kept, and its check fails with the change taken out (exit {run['exit']}): the behaviour was not there before."
    return f"{name}: it is called a regression, and its check fails with the change taken out too (exit {run['exit']}): it was broken before."


# ------------------------------------------------------------- reporting


def evidence(statement: Statement, short: bool = False) -> str:
    """What stands behind a statement's state. Short, for a table's cell."""
    state = statement.get("state")
    if state == "open":
        return "not checked" if short else "not checked: " + statement.get("because")
    with_change, without = statement.runs.get("with"), statement.runs.get("without")
    if not with_change:
        return "check not run"
    parts = [f"{with_change['outcome']} with the change"]
    if without:
        parts.append(f"{without['outcome']} without it")
    text = ", ".join(parts)
    if state == "refuted" and not short:
        text += "; observed: " + statement.get("observed")
    return text


def counts(intent: Intent) -> dict:
    return {
        "statements": len(intent.statements),
        **{state: sum(1 for s in intent.statements if s.get("state") == state) for state in STATES},
        "sources": {origin: sum(1 for s in intent.statements if s.source_from == origin) for origin in SOURCES},
    }


def ids(intent: Intent, test) -> list:
    return [statement.id for statement in intent.statements if test(statement)]


def summary_line(intent: Intent) -> str:
    c = counts(intent)
    # "author" is a reviewer's source, so it is counted only where it is used.
    sources = ", ".join(f"{c['sources'][origin]} {origin}" for origin in SOURCES if origin != "author" or c["sources"][origin])
    plural = "" if c["statements"] == 1 else "s"
    return (
        f"{c['statements']} statement{plural}: {c['checked']} checked, {c['refuted']} refuted, "
        f"{c['open']} open. Sources: {sources}."
    )


def report_text(intent: Intent, verbose: bool) -> str:
    lines = [f"{intent.path}: {intent.title or '(no title)'}"]
    for note in intent.notes:
        lines.append(f"  note: {note}")
    width = max((len(s.id) for s in intent.statements), default=2)
    for statement in intent.statements:
        lines.append(
            f"  {statement.id.ljust(width)}  {statement.get('kind').ljust(7)}  "
            f"{statement.get('state').ljust(7)}  {evidence(statement)}"
        )
        for phase in ("with", "without"):
            run = statement.runs.get(phase)
            if run and (verbose or run["outcome"] != run["wanted"]):
                lines.append(f"      {phase} the change, exit {run['exit']}, {run['seconds']}s: {statement.get('check')}")
                lines.extend(f"      | {text}" for text in run["tail"])
    lines.append("  " + summary_line(intent))
    open_ids = ids(intent, lambda s: s.get("state") == "open")
    inferred = ids(intent, lambda s: s.source_from == "inferred")
    refuted = ids(intent, lambda s: s.get("state") == "refuted")
    if refuted:
        lines.append(f"  Refuted, shown not to hold: {', '.join(refuted)}")
    if open_ids:
        lines.append(f"  Open, assumed and not checked: {', '.join(open_ids)}")
    if inferred:
        lines.append(f"  Inferred, asked for by nobody, for a person to confirm: {', '.join(inferred)}")
    if intent.problems:
        lines.append("  Problems:")
        lines.extend(f"    - {problem}" for problem in intent.problems)
    return "\n".join(lines)


def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def report_markdown(intent: Intent) -> str:
    lines = [f"### Intent: {intent.title}", "", "| | Statement | Kind | State | Evidence |", "|---|---|---|---|---|"]
    for statement in intent.statements:
        state = statement.get("state")
        shown = state if state == "checked" else f"**{state}**"
        lines.append(
            f"| {statement.id} | {cell(statement.title)} | {statement.get('kind')} | {shown} "
            f"| {cell(evidence(statement, short=True))} |"
        )
    lines += ["", summary_line(intent)]
    refuted = [statement for statement in intent.statements if statement.get("state") == "refuted"]
    if refuted:
        lines.append("- **Refuted, shown not to hold:**")
        lines += [f"  - **{statement.id}:** {statement.get('observed')}" for statement in refuted]
    still_open = [statement for statement in intent.statements if statement.get("state") == "open"]
    if still_open:
        lines.append("- **Open, assumed and not checked:**")
        lines += [f"  - **{statement.id}:** {statement.get('because')}" for statement in still_open]
    inferred = ids(intent, lambda s: s.source_from == "inferred")
    if inferred:
        lines.append(f"- **Inferred, asked for by nobody, for a person to confirm:** {', '.join(inferred)}")
    lines += [f"- {note}" for note in intent.notes]
    if intent.problems:
        lines += ["", "**Problems the check found:**"] + [f"- {problem}" for problem in intent.problems]
    return "\n".join(lines)


def report_json(intent: Intent) -> dict:
    return {
        "path": intent.path,
        "title": intent.title,
        "request": intent.request,
        "tests": intent.tests,
        "counts": counts(intent),
        "problems": intent.problems,
        "notes": intent.notes,
        "history": intent.history,
        "statements": [
            {
                "id": s.id,
                "title": s.title,
                "line": s.line,
                **{key: s.get(key) for key in FIELDS},
                "source_from": s.source_from,
                "runs": s.runs,
            }
            for s in intent.statements
        ],
    }


# ------------------------------------------------------------------ main


def check_file(path: Path, args, root: Path) -> Intent:
    try:
        text = path.read_text()
    except OSError as error:
        raise Unusable(f"{path}: {error.strerror}")
    intent = parse(str(path), text)
    base = git(root, "merge-base", args.base, "HEAD").strip() if args.base else None
    validate(intent, root, base)
    if not (args.run or args.base):
        return intent

    cache = {}
    run_all(intent, root, "with", wanted_with, args.timeout, cache)
    if not base:
        return intent

    keep_globs = [glob_regex(pattern) for pattern in intent.tests]
    own = os.path.relpath(path.resolve(), root.resolve())
    kept = lambda p: p == own or any(glob.match(p) for glob in keep_globs)  # noqa: E731
    history(intent, root, base, own, kept)
    if not any(wanted_without(statement) and statement.get("check") for statement in intent.statements):
        return intent
    if not intent.tests:
        intent.problems.append(
            "To run checks with the change taken out, the header names the files that hold the checks, "
            "such as \"- tests: tests/, *.test.ts\". They stay as they are while the rest is put back to the base."
        )
        return intent
    with TakenOut(root, base, kept) as taken:
        if not taken.entries:
            intent.notes.append("Nothing but the checks differs from the base, so there was no change to take out.")
        if taken.skipped:
            intent.notes.append("Not taken out (a submodule or nested repository): " + ", ".join(taken.skipped))
        run_all(intent, root, "without", wanted_without, args.timeout, cache)
    return intent


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="intent_check.py",
        description="Check intent files, and run the checks they name.",
    )
    parser.add_argument("files", nargs="+", help="intent files, such as intent/overdraw.md")
    parser.add_argument("--run", action="store_true", help="run each statement's check at the working tree")
    parser.add_argument("--base", metavar="REF", help="also run checks with the change since REF taken out (implies --run)")
    parser.add_argument("--format", choices=("text", "markdown", "json"), default="text")
    parser.add_argument("--timeout", type=float, default=600, metavar="SECONDS", help="for each check (default 600)")
    parser.add_argument("-v", "--verbose", action="store_true", help="show every check's output, not only the unexpected")
    args = parser.parse_args(argv)

    # A terminated run still puts the working tree back: `with` unwinds.
    def stop(signum, _frame):
        raise KeyboardInterrupt
    for name in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), stop)

    intents = []
    try:
        root = repository_root(Path.cwd())
        if root is None:
            if args.base:
                raise Unusable("--base needs a git repository, and this folder is not in one.")
            root = Path.cwd()
        else:
            leftover = restore_leftover(root)
            if leftover:
                print(leftover, file=sys.stderr)
        for name in args.files:
            intents.append(check_file(Path(name), args, root))
    except Unusable as error:
        print(f"intent_check: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("intent_check: interrupted. The working tree is as it was.", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps([report_json(intent) for intent in intents], indent=2))
    elif args.format == "markdown":
        print("\n\n".join(report_markdown(intent) for intent in intents))
    else:
        print("\n\n".join(report_text(intent, args.verbose) for intent in intents))
    return 1 if any(intent.problems for intent in intents) else 0


if __name__ == "__main__":
    sys.exit(main())
