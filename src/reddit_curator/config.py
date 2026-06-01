import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_REPO_ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    d = Path(os.environ.get("CURATOR_DATA_DIR", Path.home() / ".local/share/reddit_curator"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def seen_file() -> Path:
    return data_dir() / "seen.json"


def preferences_file() -> Path:
    return data_dir() / "preferences.md"


def dreams_dir() -> Path:
    d = data_dir() / "dreams"
    d.mkdir(parents=True, exist_ok=True)
    return d


def subreddits_file() -> Path:
    """Look for subreddits.txt in the repo root first, then the data dir."""
    repo_local = _REPO_ROOT / "subreddits.txt"
    if repo_local.exists():
        return repo_local
    return data_dir() / "subreddits.txt"


def user_agent() -> str:
    return os.environ.get(
        "REDDIT_USER_AGENT",
        "reddit-curator:v0.1 (personal curation script)",
    )


def claude_bin() -> str:
    return os.environ.get("CLAUDE_BIN", "claude")


# Ranking/consolidation are pure text tasks that need NO tools, and the input
# includes untrusted Reddit content. Run headless with EVERY tool denied (never
# --dangerously-skip-permissions) so prompt injection in scraped text cannot
# reach the shell, filesystem, or network as the bot user. These are the
# primary, in-code guardrail; the repo .claude/settings.json is secondary and
# is not even loaded from the subprocess cwd (clawdy / $HOME).
_DENIED_TOOLS = "Bash,Edit,Write,Read,WebFetch,WebSearch,NotebookEdit,Task"
CLAUDE_FLAGS = ("--permission-mode", "default", "--disallowedTools", _DENIED_TOOLS)


def claude_flags() -> list[str]:
    """Safe flags for the headless `claude -p` calls: deny all tools."""
    return list(CLAUDE_FLAGS)
