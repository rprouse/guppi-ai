"""Configuration model.

Settings load from environment variables and the project's .env file.
All runtime knobs (model, timeouts, token caps, skills dir) are surfaced
here so the rest of the code can be dependency-injected with a single
`Settings` instance.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for guppi.

    Values are read, in priority order, from:
      1. Explicit constructor arguments
      2. Environment variables (e.g. GUPPI_MODEL)
      3. A `.env` file in the current working directory
      4. Defaults defined here
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")

    model: str = Field("claude-sonnet-4-6", alias="GUPPI_MODEL")
    skills_dir: Path = Field(
        Path("~/.config/guppi/skills/").expanduser(),
        alias="GUPPI_SKILLS_DIR",
    )
    debug: bool = Field(False, alias="GUPPI_DEBUG")

    # Bash tool timeout in seconds.
    timeout: int = Field(30, alias="GUPPI_TIMEOUT")

    # Rough budget; once exceeded, oldest non-system turn-pairs are dropped.
    max_context_tokens: int = Field(80_000, alias="GUPPI_MAX_CONTEXT_TOKENS")

    # Hard cap on iterations through the agent loop.
    max_iterations: int = Field(25, alias="GUPPI_MAX_ITERATIONS")

    # Per-tool-result clip in tokens (approximate; uses 4 chars/token heuristic).
    tool_result_max_tokens: int = Field(2_000, alias="GUPPI_TOOL_RESULT_MAX_TOKENS")
