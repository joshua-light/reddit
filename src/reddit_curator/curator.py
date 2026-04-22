import json
import subprocess

from .config import claude_bin
from .feed import Post
from .state import load_preferences

_PROMPT = """You are curating a Reddit feed for a user who is tired of noise, hype cycles, and duplicate content. Return the {n} most genuinely interesting posts from the candidates below, strictly obeying the user's preferences.

<user_preferences>
{preferences}
</user_preferences>

<candidate_posts>
{posts}
</candidate_posts>

Rank by substance, novelty, and fit with the user's preferences — NOT by upvotes. Skip reposts, shallow memes, rage-bait, and anything matching the user's dislikes.

Aggressively filter out self-promotion and marketing slop. Telltale signs: a post that primarily exists to drive traffic to the author's product/blog/YouTube/newsletter/Discord/GitHub; "I built X" or "Check out my…" launch posts with no substantive discussion; recycled listicles or SEO-bait titles ("Top 10…", "X reasons why…"); thinly-veiled ads dressed as tutorials, case studies, or "lessons learned"; AI-generated filler with vague platitudes and no specific insight; recruiting/affiliate/referral posts. When in doubt between a promo post and a real discussion, drop the promo.

Return STRICT JSON only, no prose, no code fences, in this exact shape:
{{"picks": [{{"id": "<post id>", "why": "<one short sentence>"}}]}}
"""


def _format_posts(posts: list[Post]) -> str:
    chunks = []
    for p in posts:
        body = p.selftext[:400] if p.selftext else f"(link: {p.url})"
        line = (
            f"id: {p.id}\n"
            f"sub: r/{p.subreddit}\n"
            f"title: {p.title}\n"
        )
        if p.score or p.num_comments:
            line += f"score: {p.score} | comments: {p.num_comments}\n"
        line += f"body: {body}"
        chunks.append(line)
    return "\n\n---\n\n".join(chunks)


def _extract_json(raw: str) -> dict:
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < 0:
        raise RuntimeError(f"No JSON in Claude output:\n{raw[:500]}")
    return json.loads(raw[start : end + 1])


def pick_interesting(posts: list[Post], n: int = 5) -> list[tuple[Post, str]]:
    """Send candidates to the Claude CLI and return (post, reason) for the picks."""
    if not posts:
        return []
    prompt = _PROMPT.format(
        n=n,
        preferences=load_preferences(),
        posts=_format_posts(posts),
    )
    result = subprocess.run(
        [claude_bin(), "--dangerously-skip-permissions", "-p", prompt],
        capture_output=True,
        text=True,
        check=True,
    )
    data = _extract_json(result.stdout)
    by_id = {p.id: p for p in posts}
    out: list[tuple[Post, str]] = []
    for pick in data.get("picks", []):
        post = by_id.get(pick.get("id"))
        if post:
            out.append((post, pick.get("why", "")))
    return out
