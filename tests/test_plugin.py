"""Tests that the repository is a plugin an agent can load.

They read the manifests and the skills' own files. They do not show that an
agent following a skill does good work: that takes runs (skills/*/evals/).
"""
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"


def frontmatter(path):
    """The fields between the two `---` lines that open a SKILL.md."""
    text = path.read_text()
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert match, f"{path} has no frontmatter"
    fields, key = {}, None
    for line in match.group(1).splitlines():
        if line[:1] in " \t" and key:
            fields[key] = (fields[key] + " " + line.strip()).strip()
            continue
        key, _, value = line.partition(":")
        fields[key] = "" if value.strip() in (">-", ">", "|") else value.strip()
    return fields, text[match.end():]


class Plugin(unittest.TestCase):
    def test_the_manifests_name_one_plugin(self):
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
        self.assertRegex(plugin["name"], r"^[a-z][a-z0-9-]*$")
        self.assertEqual([entry["name"] for entry in market["plugins"]], [plugin["name"]])
        self.assertEqual(market["plugins"][0]["source"], "./")
        self.assertTrue(market["owner"]["name"])

    def test_there_is_a_skill_for_writing_and_one_for_reviewing(self):
        self.assertEqual(sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md")), ["intent", "intent-review"])

    def test_each_skill_is_named_after_its_folder_and_says_when_to_use_it(self):
        for path in SKILLS.glob("*/SKILL.md"):
            with self.subTest(path.parent.name):
                fields, body = frontmatter(path)
                self.assertEqual(fields["name"], path.parent.name)
                self.assertIn("Use this whenever", fields["description"])
                # Beyond this the listing cuts a description off.
                self.assertLessEqual(len(fields["description"]), 1536)
                self.assertLessEqual(len(body.splitlines()), 500)

    def test_the_writing_skill_puts_statements_before_checks_before_code(self):
        _, body = frontmatter(SKILLS / "intent" / "SKILL.md")
        steps = re.findall(r"^### \d\. (.+)$", body, re.M)
        starts = ("Write the statements", "Write each check", "Write the code")
        order = [next(i for i, step in enumerate(steps) if step.startswith(start)) for start in starts]
        self.assertEqual(order, sorted(order), steps)

    def test_every_file_a_skill_points_to_is_there(self):
        for path in SKILLS.glob("*/SKILL.md"):
            _, body = frontmatter(path)
            pointed = set(re.findall(r"`((?:\.\./intent/)?(?:references|scripts)/[\w./-]+)`", body))
            pointed |= {m.replace("${CLAUDE_SKILL_DIR}/", "") for m in re.findall(r"\$\{CLAUDE_SKILL_DIR\}/[\w./-]+", body)}
            self.assertTrue(pointed, path)
            for relative in pointed:
                with self.subTest(skill=path.parent.name, file=relative):
                    self.assertTrue((path.parent / relative).resolve().is_file(), relative)

    def test_a_skill_copied_into_a_repository_needs_nothing_from_the_plugin(self):
        # ${CLAUDE_PLUGIN_ROOT} is only filled in for an installed plugin.
        for path in SKILLS.rglob("*.md"):
            self.assertNotIn("CLAUDE_PLUGIN_ROOT", path.read_text(), path)

    def test_the_example_in_the_writing_skill_is_a_valid_intent_file(self):
        spec = importlib.util.spec_from_file_location("intent_check_for_plugin", SKILLS / "intent" / "scripts" / "intent_check.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module  # dataclasses look the module up by name
        spec.loader.exec_module(module)
        for skill, wanted in (("intent", 4), ("intent-review", 1)):
            _, body = frontmatter(SKILLS / skill / "SKILL.md")
            blocks = [b for b in re.findall(r"```markdown\n(.*?)```", body, re.S) if "\n## " in b or b.startswith("## ")]
            self.assertEqual(len(blocks), 1, skill)
            text = blocks[0] if blocks[0].startswith("# Intent:") else "# Intent: example\n\n> the request\n\n" + blocks[0]
            intent = module.parse("example.md", text)
            self.assertEqual(len(intent.statements), wanted)
            module.validate(intent, ROOT)
            # The examples name files of a repository that is not this one.
            problems = [problem for problem in intent.problems if "which is not a file here" not in problem]
            self.assertEqual(problems, [], skill)

    def load_script(self):
        spec = importlib.util.spec_from_file_location("intent_check_for_plugin", SKILLS / "intent" / "scripts" / "intent_check.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def test_the_format_reference_lists_the_fields_and_sources_the_script_knows(self):
        module = self.load_script()
        text = (SKILLS / "intent" / "references" / "format.md").read_text()
        fields = re.findall(r"^\| `(\w+)` \| (?:always|`checked`|`refuted`|`open`|never)", text, re.M)
        self.assertEqual(sorted(fields), sorted(module.FIELDS))
        self.assertEqual(re.findall(r"^\| `(\w+)` \| `\1: ", text, re.M), list(module.SOURCES))
        for word in module.KINDS + module.STATES:
            self.assertIn(f"`{word}`", text)

    def test_no_test_case_sits_inside_a_skill_folder(self):
        # An agent that lists a skill's folder must not find what a case expects of it.
        self.assertEqual([str(path) for path in SKILLS.rglob("case.yaml")], [])
        cases = sorted(path.parent.name for path in (ROOT / "evals").rglob("case.yaml"))
        self.assertEqual(cases, ["keeps-slugify", "refuses-overdraw", "reviews-overdraw-change"])

    def test_each_case_has_a_prompt_graders_and_a_script_that_builds_its_repository(self):
        for case in (ROOT / "evals").rglob("case.yaml"):
            with self.subTest(case.parent.name):
                self.assertIn(f"name: {case.parent.name}", case.read_text())
                self.assertTrue((case.parent / "prompt.md").read_text().startswith("---\ntags:"))
                self.assertTrue(list((case.parent / "graders").glob("*.md")))
                self.assertIn("scaffold_script: place-files.sh", case.read_text())
                self.assertTrue((case.parent / "place-files.sh").is_file())


if __name__ == "__main__":
    unittest.main()
