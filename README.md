# Claude Usage — SwiftBar plugin

Live Claude Code plan usage in your macOS menu bar — the same 5-hour and weekly
rate-limit numbers as `/usage`, without opening anything.

A small **circular ring gauge** with the 5-hour utilization **% in the middle**.
The ring fills clockwise as you approach your limit. In its normal state it's a
**template image**, so macOS tints it to match the menu bar exactly like the
native clock/battery icons — **black over a light wallpaper, white over a dark
one**. At **70%** it turns **orange** and at **90%** **red** (drawn as a real
colored icon so the alert reads on any background).

Click it for the full breakdown: 5-hour, weekly, weekly-Opus, resets, a **trend
sparkline** of recent 5-hour usage, and a **time-to-cap projection** ("~24m to
5h cap at current rate") computed from your burn rate.

## Install

```bash
git clone https://github.com/heyodog0/claude-usage-swiftbar.git
cd claude-usage-swiftbar && ./install.sh
```

Installs SwiftBar and Pillow (via [Homebrew](https://brew.sh)) if needed, links
the plugin, and reloads. **First run:** macOS shows a Keychain prompt for
`Claude Code-credentials` → click **Always Allow**. Requires Claude Code signed in.

## How it works

Calls the same endpoint Claude Code's `/usage` uses
(`GET https://api.anthropic.com/api/oauth/usage`) with the OAuth token Claude
Code already stores in your Keychain. **The token never leaves your machine**
except in the request to Anthropic's own API — no secrets in this repo.

The ring icon is drawn with **[Pillow](https://python-pillow.org)**, so the
plugin runs on Homebrew's Python (the shebang is `#!/opt/homebrew/bin/python3`).
If Pillow ever isn't available it **falls back to a plain `NN%` text title** —
the numbers still show, just without the ring.

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

- **Warning colors:** `WARN_PCT` (orange) and `CRIT_PCT` (red) in the `CONFIG` block.
- **Ring look:** the `ring_icon()` helper — `RING_WEIGHT` (digit weight, e.g.
  Light/Regular/Medium/Semibold), `pt` (overall size), the `W * 0.10` stroke
  width, and `TRACK_COL` (the unfilled-ring color).
- **Refresh rate:** rename the file — `claude-usage.30s.py`, `claude-usage.5m.py`, etc.

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
