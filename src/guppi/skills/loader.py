"""Scan a directory for SKILL.md files and load them into Skill objects.

File layout expected:
    <skills_dir>/<skill-name>/SKILL.md
where SKILL.md begins with a YAML frontmatter block delimited by `---`
and contains a markdown body beneath.

Example SKILL.md:
    ---
    name: git-safety
    description: Safe git operations; confirm before destructive commands
    triggers: [git, commit, push, rebase]
    ---
    When the user asks for destructive git operations...
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from .skill import Skill

log = logging.getLogger(__name__)

_FRONTMATTER_DELIM = "---"


def _parse_skill_file(path: Path) -> Skill | None:
    """Parse a single SKILL.md file; return None on failure (with a warning)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        log.warning("skipping %s: %s", path, e)
        return None

    lines = text.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_DELIM:
        log.warning("skipping %s: no frontmatter", path)
        return None

    # Find the closing delimiter.
    try:
        end = next(i for i, ln in enumerate(lines[1:], start=1) if ln.strip() == _FRONTMATTER_DELIM)
    except StopIteration:
        log.warning("skipping %s: unterminated frontmatter", path)
        return None

    frontmatter_text = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1 :])

    try:
        meta = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError as e:
        log.warning("skipping %s: invalid YAML frontmatter: %s", path, e)
        return None

    name = meta.get("name")
    description = meta.get("description")
    if not name or not description:
        log.warning("skipping %s: missing required `name` or `description`", path)
        return None

    triggers = meta.get("triggers") or []
    if not isinstance(triggers, list):
        triggers = [str(triggers)]

    return Skill(
        name=str(name),
        description=str(description),
        body=body,
        source=path,
        triggers=[str(t) for t in triggers],
    )


def load_skills(skills_dir: Path) -> list[Skill]:
    """Return every valid Skill found beneath `skills_dir`.

    Missing directory is treated as "no skills" — not an error. Invalid
    skill files are logged and skipped so one broken file can't take
    down the whole session.
    """
    if not skills_dir.exists():
        log.info("skills dir %s does not exist; no skills loaded", skills_dir)
        return []

    skills: list[Skill] = []
    for skill_md in sorted(skills_dir.rglob("SKILL.md")):
        skill = _parse_skill_file(skill_md)
        if skill is not None:
            skills.append(skill)
    return skills


def select_relevant_skills(skills: list[Skill], _user_message: str | None = None) -> list[Skill]:
    """Pick which skills to include for this session.

    Today: load all. Future: keyword/description matching or embedding
    retrieval based on `_user_message` (and maybe the running history).
    """
    return list(skills)


def build_system_prompt(base_prompt: str, skills: list[Skill]) -> str:
    """Append selected skill bodies to the base system prompt."""
    if not skills:
        return base_prompt
    sections = "\n\n".join(s.as_prompt_section() for s in skills)
    return f"{base_prompt}\n\n# Available skills\n\n{sections}"
