"""The Skill dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Skill:
    """A single skill loaded from disk.

    Fields:
      name: short identifier (matches the YAML `name` key)
      description: one-line summary used for selection and prompts
      triggers: optional list of keywords/phrases hinting when to apply
      body: the markdown body (sans frontmatter) — this is what gets
            injected into the system prompt
      source: the file path on disk, for debugging
    """

    name: str
    description: str
    body: str
    source: Path
    triggers: list[str] = field(default_factory=list)

    def as_prompt_section(self) -> str:
        """Render this skill as a heading + body block for the system prompt."""
        return f"## Skill: {self.name}\n\n_{self.description}_\n\n{self.body.strip()}\n"
