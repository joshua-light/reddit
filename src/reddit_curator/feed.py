import time
from dataclasses import dataclass

import httpx

from .config import subreddits_file, user_agent

_SUBS_PER_REQUEST = 15
_CHUNK_DELAY_S = 4.0
_TIMEOUT_S = 15.0
_RETRY_BACKOFF_S = 12.0


@dataclass
class Post:
    id: str
    subreddit: str
    title: str
    selftext: str
    url: str
    permalink: str
    score: int
    num_comments: int
    over_18: bool
    stickied: bool
    author: str


def load_subreddits() -> list[str]:
    path = subreddits_file()
    if not path.exists():
        raise RuntimeError(
            f"No subreddits file at {path}. Add one subreddit name per line."
        )
    subs: list[str] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("r/"):
            line = line[2:]
        subs.append(line)
    return subs


def _fetch_chunk(client: httpx.Client, url: str, limit: int) -> list[Post]:
    for attempt in (0, 1):
        resp = client.get(url, params={"limit": limit, "raw_json": 1})
        if resp.status_code in (403, 429, 503) and attempt == 0:
            time.sleep(_RETRY_BACKOFF_S)
            continue
        resp.raise_for_status()
        return _parse_listing(resp.json())
    resp.raise_for_status()
    return []


def _parse_listing(payload: dict) -> list[Post]:
    out: list[Post] = []
    for child in payload.get("data", {}).get("children", []):
        if child.get("kind") != "t3":
            continue
        d = child.get("data", {})
        out.append(
            Post(
                id=d["id"],
                subreddit=d.get("subreddit", ""),
                title=d.get("title", ""),
                selftext=(d.get("selftext") or "")[:1000],
                url=d.get("url", ""),
                permalink=f"https://reddit.com{d.get('permalink', '')}",
                score=int(d.get("score", 0)),
                num_comments=int(d.get("num_comments", 0)),
                over_18=bool(d.get("over_18", False)),
                stickied=bool(d.get("stickied", False)),
                author=d.get("author", ""),
            )
        )
    return out


def fetch_frontpage(
    limit: int = 100,
    listing: str = "hot",
    subreddits: list[str] | None = None,
) -> list[Post]:
    """Pull posts from the configured subreddits via Reddit's public JSON API.

    listing: "hot" | "new" | "top" | "rising"
    """
    subs = subreddits if subreddits is not None else load_subreddits()
    if not subs:
        return []

    per_chunk = max(25, min(100, limit))
    headers = {
        "User-Agent": user_agent(),
        "Accept": "application/json",
    }
    posts: list[Post] = []

    chunks = [subs[i : i + _SUBS_PER_REQUEST] for i in range(0, len(subs), _SUBS_PER_REQUEST)]
    for idx, chunk in enumerate(chunks):
        multi = "+".join(chunk)
        url = f"https://www.reddit.com/r/{multi}/{listing}.json"
        # fresh client per chunk: Reddit flags connection reuse as bot-like
        with httpx.Client(headers=headers, timeout=_TIMEOUT_S) as client:
            posts.extend(_fetch_chunk(client, url, per_chunk))
        if idx < len(chunks) - 1:
            time.sleep(_CHUNK_DELAY_S)

    posts.sort(key=lambda p: p.score, reverse=True)
    return posts[:limit]


def deduplicate(posts: list[Post]) -> list[Post]:
    """Drop stickied/mod posts, exact URL repeats, and near-identical titles."""
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    out: list[Post] = []
    for p in posts:
        if p.stickied:
            continue
        norm = " ".join(p.title.lower().split())[:80]
        if p.url in seen_urls or norm in seen_titles:
            continue
        seen_urls.add(p.url)
        seen_titles.add(norm)
        out.append(p)
    return out
