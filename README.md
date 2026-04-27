# reddit-curator

A Reddit feed reader that uses Claude to filter out the noise.

Pulls hot/new/top posts from the subreddits you list, drops reposts and
self-promo, then asks the Claude CLI to pick the `N` most genuinely
interesting ones based on your written preferences.

## Requirements

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) (or `pip`)
- The [Claude Code CLI](https://docs.claude.com/en/docs/claude-code) installed
  and authenticated (`claude` on your `PATH`)

## Install

```sh
git clone https://github.com/joshua-light/reddit.git reddit-curator
cd reddit-curator
uv sync
```

Create `subreddits.txt` in the repo root — one subreddit per line, with
optional comma-separated tags after the name.

## Usage

```sh
# Pull the frontpage, filter via Claude, show top 5
uv run curator fetch

# More candidates, fewer picks, only AI-tagged subs
uv run curator fetch --limit 200 -n 3 --tag ai

# Add an ad-hoc focus for this query only
uv run curator fetch --focus "new model releases"

# Mark a post as uninteresting (writes to preferences.md)
uv run curator dislike <post_id> -r "too much hype"

# Add a free-form preference rule
uv run curator why too much AI hype this week

# Print current preferences / list configured tags
uv run curator prefs
uv run curator tags
```

State (seen posts, preferences) lives in `~/.local/share/reddit_curator/` by
default — override with `CURATOR_DATA_DIR`.

## Configuration

All env vars are optional; see `.env.example`.

| Var                 | Default                                              |
| ------------------- | ---------------------------------------------------- |
| `CURATOR_DATA_DIR`  | `~/.local/share/reddit_curator`                      |
| `REDDIT_USER_AGENT` | `reddit-curator:v0.1 (personal curation script)`     |
| `CLAUDE_BIN`        | `claude`                                             |

## License

MIT — see [LICENSE](LICENSE).
