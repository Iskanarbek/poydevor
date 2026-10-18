#!/usr/bin/env python3
"""Local dev entry point: loads local_env.sh's variables into this process,
then runs the normal Django dev server. Exists so `.claude/launch.json` (and
anyone running this by hand) doesn't need a shell to source local_env.sh —
just:  venv/bin/python3 dev_server.py
"""
import os
import re
import sys
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent / "local_env.sh"
_EXPORT_LINE = re.compile(r'^export\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$')


def load_local_env(path: Path) -> None:
    """A tiny, good-enough parser for this project's own local_env.sh: one
    `export NAME="value"` (or unquoted) per line, '#' comments, blank lines.
    Doesn't handle general shell syntax — it isn't meant to."""
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _EXPORT_LINE.match(line)
        if not match:
            continue
        name, raw_value = match.group(1), match.group(2).strip()
        if raw_value[:1] in ("'", '"'):
            # Quoted value: take everything up to the matching closing quote and
            # discard the rest of the line (a trailing "# ..." comment, if any).
            quote = raw_value[0]
            end = raw_value.find(quote, 1)
            value = raw_value[1:end] if end != -1 else raw_value[1:]
        else:
            # Unquoted: a trailing "# comment" is still a comment.
            value = raw_value.split(" #", 1)[0].strip()
        value = value.replace('\\$', '$')  # local_env.sh escapes literal "$" inside double quotes
        # Don't override a value the environment already supplies (e.g. a real
        # deployment host setting these for real, rather than through this file).
        os.environ.setdefault(name, value)


if __name__ == "__main__":
    load_local_env(ENV_FILE)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "poydevor.settings")
    sys.argv = [sys.argv[0], "runserver", "8080"]
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
