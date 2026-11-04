"""Guards against template text leaking into pages (e.g. a multi-line {# ... #} comment, which
Django does NOT treat as a comment and prints as plain text)."""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class TemplateHygieneTests(SimpleTestCase):
    def templates(self):
        return sorted(Path(settings.BASE_DIR, "templates").rglob("*.html"))

    def test_no_comment_runs_over_several_lines(self):
        problems = []
        for path in self.templates():
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if "{#" in line and "#}" not in line.split("{#", 1)[1]:
                    problems.append(f"{path.name}:{number}")
        self.assertEqual(problems, [], "Use {% comment %}...{% endcomment %} for multi-line comments")

    def test_no_unbalanced_template_tags_in_text(self):
        for path in self.templates():
            text = path.read_text()
            self.assertEqual(text.count("{{"), text.count("}}"), path.name)
            self.assertEqual(len(re.findall(r"\{%", text)), len(re.findall(r"%\}", text)), path.name)
