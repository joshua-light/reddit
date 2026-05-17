import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

from .config import subreddits_file, user_agent

_SUBS_PER_REQUEST = 15
_CHUNK_DELAY_S = 4.0
_TIMEOUT_S = 15.0
_RETRY_BACKOFF_S = 12.0
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


@dataclass
class Post:
    id: str
    subreddit: str
    title: str
    selftext: str
    url: str
    permalink: str
    author: str = ""
    score: int = 0
    num_comments: int = 0
    over_18: bool = False
    stickied: bool = False


@dataclass
class SubSpec:
    name: str
    tags: list[str]


def _parse_subreddits_file() -> list[SubSpec]:
    path = subreddits_file()
    if not path.exists():
        raise RuntimeError(
            f"No subreddits file at {path}. Add one subreddit name per line."
        )
    specs: list[SubSpec] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        name = parts[0]
        if name.lower().startswith("r/"):
            name = name[2:]
        tags: list[str] = []
        if len(parts) == 2:
            tags = [t.strip().lower() for t in parts[1].split(",") if t.strip()]
        specs.append(SubSpec(name=name, tags=tags))
    return specs


def load_subreddits(tag: str | None = None) -> list[str]:
    specs = _parse_subreddits_file()
    if tag:
        t = tag.lower()
        specs = [s for s in specs if t in s.tags]
    return [s.name for s in specs]


def all_tags() -> dict[str, int]:
    """Return a mapping of tag → number of subreddits carrying that tag."""
    counts: dict[str, int] = {}
    for spec in _parse_subreddits_file():
        for t in spec.tags:
            counts[t] = counts.get(t, 0) + 1
    return counts


_TAG_RE = re.compile(r"<[^>]+>")
_SC_RE = re.compile(r"<!-- SC_OFF -->(.*?)<!-- SC_ON -->", re.DOTALL)
_WS_RE = re.compile(r"\s+")
_LINK_RE = re.compile(r'<a href="([^"]+)"[^>]*>\[link\]</a>')


def _unescape(s: str) -> str:
    return (
        s.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#32;", " ")
        .replace("&#39;", "'")
    )


def _extract_selftext(html_content: str) -> str:
    m = _SC_RE.search(html_content)
    if not m:
        return ""
    stripped = _TAG_RE.sub("", m.group(1))
    return _WS_RE.sub(" ", _unescape(stripped)).strip()[:3500]


def _extract_external_link(html_content: str, fallback: str) -> str:
    m = _LINK_RE.search(html_content)
    return _unescape(m.group(1)) if m else fallback


def _parse_atom(xml_bytes: bytes) -> list[Post]:
    root = ET.fromstring(xml_bytes)
    out: list[Post] = []
    for entry in root.findall("atom:entry", _ATOM_NS):
        atom_id_el = entry.find("atom:id", _ATOM_NS)
        if atom_id_el is None or not atom_id_el.text:
            continue
        raw_id = atom_id_el.text
        post_id = raw_id[3:] if raw_id.startswith("t3_") else raw_id

        title_el = entry.find("atom:title", _ATOM_NS)
        title = (title_el.text or "") if title_el is not None else ""

        link_el = entry.find("atom:link", _ATOM_NS)
        permalink = link_el.get("href", "") if link_el is not None else ""

        cat_el = entry.find("atom:category", _ATOM_NS)
        subreddit = cat_el.get("term", "") if cat_el is not None else ""

        author_el = entry.find("atom:author/atom:name", _ATOM_NS)
        author_raw = (author_el.text or "") if author_el is not None else ""
        author = author_raw.removeprefix("/u/").removeprefix("u/")

        content_el = entry.find("atom:content", _ATOM_NS)
        content_html = (content_el.text or "") if content_el is not None else ""
        selftext = _extract_selftext(content_html)
        url = _extract_external_link(content_html, permalink)

        out.append(
            Post(
                id=post_id,
                subreddit=subreddit,
                title=title,
                selftext=selftext,
                url=url,
                permalink=permalink,
                author=author,
            )
        )
    return out


def _fetch_chunk(client: httpx.Client, url: str, limit: int) -> list[Post]:
    params = {"limit": limit}
    for attempt in (0, 1):
        resp = client.get(url, params=params)
        if resp.status_code in (403, 429, 503) and attempt == 0:
            time.sleep(_RETRY_BACKOFF_S)
            continue
        resp.raise_for_status()
        return _parse_atom(resp.content)
    resp.raise_for_status()
    return []


def fetch_frontpage(
    limit: int = 100,
    listing: str = "hot",
    subreddits: list[str] | None = None,
    tag: str | None = None,
) -> list[Post]:
    """Pull posts from the configured subreddits via Reddit's public Atom feeds.

    listing: "hot" | "new" | "top" | "rising"
    tag: if set, only fetch subs carrying this tag.
    """
    subs = subreddits if subreddits is not None else load_subreddits(tag=tag)
    if not subs:
        return []

    per_chunk = max(25, min(100, limit))
    headers = {"User-Agent": user_agent()}

    chunks = [subs[i : i + _SUBS_PER_REQUEST] for i in range(0, len(subs), _SUBS_PER_REQUEST)]
    chunk_posts: list[list[Post]] = []
    for idx, chunk in enumerate(chunks):
        multi = "+".join(chunk)
        # .rss (Atom): works from cloud IPs that Reddit blocks on .json
        url = f"https://www.reddit.com/r/{multi}/{listing}.rss"
        with httpx.Client(headers=headers, timeout=_TIMEOUT_S) as client:
            chunk_posts.append(_fetch_chunk(client, url, per_chunk))
        if idx < len(chunks) - 1:
            time.sleep(_CHUNK_DELAY_S)

    # Round-robin merge: each chunk is already in Reddit's hot order; interleaving
    # prevents later chunks from being squeezed out when `limit` truncates.
    merged: list[Post] = []
    max_len = max((len(cp) for cp in chunk_posts), default=0)
    for i in range(max_len):
        for cp in chunk_posts:
            if i < len(cp):
                merged.append(cp[i])
    return merged[:limit]


def deduplicate(posts: list[Post]) -> list[Post]:
    """Drop exact URL repeats and near-identical titles."""
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
