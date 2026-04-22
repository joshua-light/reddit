import json
from datetime import datetime, timezone

from .config import preferences_file, seen_file
from .feed import Post

DEFAULT_PREFERENCES = """# Reddit curator preferences

This file shapes what the curator picks for you. Edit freely in natural language —
each rule is just a line the model reads. `curator dislike` and `curator why` append here.

## Likes
- substantive discussions, technical deep-dives, original reporting, novel ideas

## Dislikes
- reposts and recycled hype cycles
- low-effort memes and rage-bait
- generic "X is dead" / "Y killed Z" headlines
"""

_SEEN_CAP = 1000


def load_seen() -> dict[str, dict]:
    p = seen_file()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return {}


def _save_seen(seen: dict[str, dict]) -> None:
    if len(seen) > _SEEN_CAP:
        ordered = sorted(seen.items(), key=lambda kv: kv[1].get("shown_at", ""), reverse=True)
        seen = dict(ordered[:_SEEN_CAP])
    seen_file().write_text(json.dumps(seen, indent=2))


def record_shown(posts: list[Post]) -> None:
    seen = load_seen()
    now = datetime.now(timezone.utc).isoformat()
    for p in posts:
        seen[p.id] = {
            "title": p.title,
            "subreddit": p.subreddit,
            "permalink": p.permalink,
            "shown_at": now,
        }
    _save_seen(seen)


def load_preferences() -> str:
    p = preferences_file()
    if not p.exists():
        p.write_text(DEFAULT_PREFERENCES)
    return p.read_text()


def append_preference(line: str) -> None:
    load_preferences()  # ensure file exists with defaults
    with preferences_file().open("a") as f:
        f.write(f"- {line.strip()}\n")


def record_dislike(post_id: str, reason: str = "") -> str:
    """Append a dislike entry for post_id, using seen.json metadata if available."""
    seen = load_seen()
    meta = seen.get(post_id)
    if meta:
        entry = f"disliked r/{meta['subreddit']}: {meta['title']!r}"
    else:
        entry = f"disliked post id {post_id}"
    if reason:
        entry += f" — {reason}"
    append_preference(entry)
    return entry
