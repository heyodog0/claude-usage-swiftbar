# Claude Usage — SwiftBar plugin

Live Claude Code plan usage in your macOS menu bar — the same 5-hour and weekly
rate-limit numbers as `/usage`, without opening anything.

```
▰▰▱▱▱ 42%
```

The bar fills as you approach your limit and turns **orange at 70%**, **red at
90%** (otherwise it's the normal menu-bar color, for readability). Click it for
the full breakdown: 5-hour, weekly, weekly-Opus, resets, a **trend sparkline**
of recent 5-hour usage, and a **time-to-cap projection** ("~24m to 5h cap at
current rate") computed from your burn rate.

## Install

```bash
git clone https://github.com/heyodog0/claude-usage-swiftbar.git
cd claude-usage-swiftbar && ./install.sh
```

Installs SwiftBar (via [Homebrew](https://brew.sh)) if needed, links the plugin,
and reloads. **First run:** macOS shows a Keychain prompt for
`Claude Code-credentials` → click **Always Allow**. Requires Claude Code signed in.

## How it works

Calls the same endpoint Claude Code's `/usage` uses
(`GET https://api.anthropic.com/api/oauth/usage`) with the OAuth token Claude
Code already stores in your Keychain. **The token never leaves your machine**
except in the request to Anthropic's own API — no secrets in this repo.

**Easy on the endpoint.** Although the menu bar refreshes every minute, it only
*calls* the API every ~10 min (cached in between), and on a `429` it honors
`Retry-After` and backs off ~30 min while still showing the last good numbers —
so you won't hammer the rate limit. Tune with `FETCH_TTL` / `BACKOFF_429`.

It's an **unofficial endpoint**, so it's built to degrade, not break: if the
live call fails (expired token, API change, offline) and there's no cached
value yet, it falls back to a local token estimate marked `⚠`. The endpoint,
headers, cadence, and color thresholds are all `CONFIG` constants at the top of
`claude-usage.1m.py`.

## Tweak

- Colors / bar width: `WARN_PCT`, `CRIT_PCT`, `BAR_SEGMENTS` in the `CONFIG` block.
- Refresh rate: rename the file — `claude-usage.30s.py`, `claude-usage.5m.py`, etc.

## Sync across Macs

`install.sh` symlinks the plugin from this repo, so updating is just:

```bash
git pull && open "swiftbar://refreshallplugins"
```

## Uninstall

```bash
./uninstall.sh                    # remove the plugin
brew uninstall --cask swiftbar    # remove SwiftBar too (optional)
```

MIT © Ryan Truong. Not affiliated with Anthropic; uses an unofficial endpoint that may change.
