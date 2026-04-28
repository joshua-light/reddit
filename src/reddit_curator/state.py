import json
import re
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

_SEEN_CAP = 100

_TOK_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "of", "in", "on", "at", "to", "for", "with", "and", "or", "but", "if",
        "then", "this", "that", "these", "those", "i", "you", "he", "she",
        "it", "we", "they", "my", "your", "his", "her", "its", "our", "their",
        "just", "new", "what", "why", "how", "when", "where", "who", "which",
        "not", "do", "does", "did", "has", "have", "had", "will", "would",
        "can", "could", "should", "may", "might", "via", "amp", "from", "by",
        "as", "so", "than", "into", "out", "up", "down", "over", "about",
    }
)


def _title_tokens(title: str) -> set[str]:
    out: set[str] = set()
    for t in _TOK_RE.findall(title.lower()):
        if t in _STOPWORDS:
            continue
        # keep digit-only tokens (years, version numbers) even when short
        if t.isdigit() or len(t) > 1:
            out.add(t)
    return out


def _is_similar_title(a: set[str], b: set[str]) -> bool:
    """Loose fuzzy match: high token overlap means we've already shown this story."""
    if not a or not b:
        return False
    inter = len(a & b)
    if inter < 2:
        return False
    union = len(a | b)
    jaccard = inter / union
    smaller = min(len(a), len(b))
    coverage = inter / smaller
    return jaccard >= 0.4 or (coverage >= 0.6 and smaller >= 3)


def filter_unseen(posts: list[Post], seen: dict | None = None) -> tuple[list[Post], int]:
    """Drop posts already shown, by id or by loosely-matching title.

    Returns (kept_posts, hidden_count).
    """
    if seen is None:
        seen = load_seen()
    seen_token_sets = [_title_tokens(meta.get("title", "")) for meta in seen.values()]
    seen_token_sets = [s for s in seen_token_sets if s]
    out: list[Post] = []
    for p in posts:
        if p.id in seen:
            continue
        toks = _title_tokens(p.title)
        if any(_is_similar_title(toks, s) for s in seen_token_sets):
            continue
        out.append(p)
    return out, len(posts) - len(out)


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


def record_love(post_id: str) -> str:
    """Append a love entry for post_id, using seen.json metadata if available."""
    seen = load_seen()
    meta = seen.get(post_id)
    if meta:
        entry = f"loved r/{meta['subreddit']}: {meta['title']!r}"
    else:
        entry = f"loved post id {post_id}"
    append_preference(entry)
    return entry
