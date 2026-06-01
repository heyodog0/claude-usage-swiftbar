# Claude Usage — SwiftBar plugin

Live **Claude Code plan usage** in your macOS menu bar — the same 5-hour and
weekly rate-limit numbers you'd see from `/usage`, without opening anything.

```
▰▰▱▱▱ 42%
```

The bar fills and shifts **green → orange → red** as you approach your limit.
Click it for the full breakdown: 5-hour window, weekly (all models), weekly
Opus, and when each resets.

<sub>Headline shows the *binding* window — whichever of 5h / weekly is closest
to its limit. The dropdown always shows all of them.</sub>

## Install

```bash
git clone https://github.com/heyodog0/claude-usage-swiftbar.git
cd claude-usage-swiftbar
./install.sh
```

The installer adds SwiftBar (via Homebrew) if you don't have it, links the
plugin, and reloads. **On first run, macOS shows a Keychain prompt** for
`Claude Code-credentials` — click **Always Allow**. Done.

Requirements: macOS, [Homebrew](https://brew.sh), and Claude Code signed in.

## How it works

It calls the same endpoint Claude Code's `/usage` uses:

```
GET https://api.anthropic.com/api/oauth/usage
Authorization: Bearer <your OAuth token>
anthropic-beta: oauth-2025-04-20
anthropic-version: 2023-06-01
```

The token is read locally from `~/.claude/.credentials.json` or your macOS
Keychain (`Claude Code-credentials`) — the same token Claude Code already
stores and keeps refreshed. **Your token never leaves your machine** except in
the request to Anthropic's own API. There are no secrets in this repo.

### Built to degrade, not break

This uses an **unofficial** endpoint, so it's defensive by design:

1. **Graceful fallback** — if the live call fails for any reason (token
   expired, endpoint changed, offline), it falls back to a local token/cost
   estimate parsed from `~/.claude/projects/**/*.jsonl` and marks it `⚠`.
   The menu bar is never blank or broken.
2. **Last-good cache** — a transient failure still shows the last successful
   reading (with its age) from `~/.swiftbar-plugins/.claude-usage-cache.json`.
3. **One-line config** — the endpoint URL, beta-header version, keychain name,
   and color thresholds are all `CONFIG` constants at the top of
   `claude-usage.1m.py`. If Anthropic ever changes the API, it's a quick edit.

## Configure

Edit the `CONFIG` block at the top of `claude-usage.1m.py`:

| Constant | Default | Meaning |
|---|---|---|
| `WARN_PCT` | `70` | % at which the gauge turns orange |
| `CRIT_PCT` | `90` | % at which it turns red |
| `BAR_SEGMENTS` | `5` | width of the mini bar |

Change the refresh interval by renaming the file — the `1m` encodes it:
`claude-usage.30s.py` (30s), `claude-usage.5m.py` (5 min), etc.

## Sync across Macs

`install.sh` **symlinks** the plugin from this repo into
`~/.swiftbar-plugins`, so on each machine:

```bash
git pull && open "swiftbar://refreshallplugins"
```

picks up the latest version. Set it up once per Mac with `./install.sh`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Blank `?` icon | A stray `__pycache__` was created; `rm -rf ~/.swiftbar-plugins/__pycache__` and reload. (Running as a script — the default — never creates one.) |
| `▱▱▱▱▱ ⚠` | Live call failed. Open the dropdown for the **Reason**. Usually an expired token — open Claude Code once to refresh it. |
| No Keychain prompt / always `⚠` | Run the plugin directly to see the error: `~/.swiftbar-plugins/claude-usage.1m.py` |

## Uninstall

```bash
./uninstall.sh                       # remove the plugin
brew uninstall --cask swiftbar       # remove SwiftBar too (optional)
```

## License

MIT © Ryan Truong. Not affiliated with Anthropic. Uses an unofficial endpoint
that may change at any time.
