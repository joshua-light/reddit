import click

from .curator import pick_interesting
from .feed import all_tags, deduplicate, fetch_frontpage
from .state import (
    append_preference,
    load_preferences,
    load_seen,
    record_dislike,
    record_shown,
)


@click.group()
def cli():
    """Reddit curator — filtered feed powered by Claude CLI."""


@cli.command()
@click.option("--limit", default=100, show_default=True, help="Candidate posts to pull.")
@click.option("-n", default=5, show_default=True, help="How many picks to show.")
@click.option("--listing", default="hot", show_default=True,
              type=click.Choice(["hot", "new", "top", "best", "rising"]))
@click.option("--include-seen", is_flag=True, help="Include already-shown posts.")
@click.option("--tag", default=None, help="Only fetch subs carrying this tag.")
@click.option("--focus", default=None,
              help="Ad-hoc focus for this query only (e.g. 'new model releases').")
def fetch(limit, n, listing, include_seen, tag, focus):
    """Pull your subscribed-subs frontpage, filter via Claude, show top N."""
    if tag and tag.lower() not in all_tags():
        known = ", ".join(sorted(all_tags())) or "(none)"
        raise click.BadParameter(f"unknown tag {tag!r}. Known: {known}", param_hint="--tag")
    posts = fetch_frontpage(limit=limit, listing=listing, tag=tag)
    posts = deduplicate(posts)
    if not include_seen:
        seen = load_seen()
        posts = [p for p in posts if p.id not in seen]
    if not posts:
        click.echo("No candidate posts after filtering.")
        return
    picks = pick_interesting(posts, n=n, focus=focus)
    if not picks:
        click.echo("Claude returned no picks.")
        return
    for p, why in picks:
        meta = f"r/{p.subreddit}  ({p.id})"
        if p.score or p.num_comments:
            meta = f"[{p.score}↑ {p.num_comments}💬] {meta}"
        click.echo(f"\n{meta}")
        click.echo(f"  {p.title}")
        click.echo(f"  → {why}")
        click.echo(f"  {p.permalink}")
    record_shown([p for p, _ in picks])


@cli.command()
@click.argument("post_id")
@click.option("-r", "--reason", default="", help="Why it wasn't interesting.")
def dislike(post_id, reason):
    """Mark a post as uninteresting; writes to preferences.md."""
    entry = record_dislike(post_id, reason=reason)
    click.echo(f"Recorded: {entry}")


@cli.command()
@click.argument("rule", nargs=-1, required=True)
def why(rule):
    """Add a free-form preference rule (e.g. `curator why too much AI hype`)."""
    text = " ".join(rule)
    append_preference(text)
    click.echo(f"Added preference: {text}")


@cli.command()
def prefs():
    """Print the current preferences file."""
    click.echo(load_preferences())


@cli.command()
def tags():
    """List tags configured in subreddits.txt with sub counts."""
    counts = all_tags()
    if not counts:
        click.echo("No tags configured.")
        return
    for t, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        click.echo(f"  {t}: {n}")


if __name__ == "__main__":
    cli()
