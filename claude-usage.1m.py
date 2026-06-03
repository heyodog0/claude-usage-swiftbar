#!/usr/bin/env python3
"""
SwiftBar plugin: Claude plan usage at a glance.

PRIMARY: live plan rate-limit % (5-hour window + weekly) from Anthropic's
         /api/oauth/usage endpoint — the same data `/usage` shows in-app.
FALLBACK: if the live call fails for ANY reason (token expired, endpoint
          changed, offline), it degrades to a local token/cost estimate
          parsed from ~/.claude/projects/**/*.jsonl and marks it with ⚠.

Designed to degrade, never break. If the menu bar shows "⚠ est", the live
endpoint was unreachable; open Claude Code once to refresh your token, or
check the CONFIG block below if Anthropic changed the API.
"""
import json, os, glob, time, subprocess, random, urllib.request, urllib.error
from datetime import datetime, timezone

# ─────────────────────────── CONFIG (edit here if API changes) ──────────────
USAGE_URL      = "https://api.anthropic.com/api/oauth/usage"
ANTHROPIC_BETA = "oauth-2025-04-20"
ANTHROPIC_VER  = "2023-06-01"
USER_AGENT     = "claude-cli/usage-widget (external)"
KEYCHAIN_NAME  = "Claude Code-credentials"
CREDS_FILE     = os.path.expanduser("~/.claude/.credentials.json")
CACHE_FILE     = os.path.expanduser("~/.swiftbar-plugins/.claude-usage-cache.json")
CLAUDE_DIR     = os.path.expanduser("~/.claude/projects")
HTTP_TIMEOUT   = 6
WARN_PCT       = 70    # orange at/above this
CRIT_PCT       = 90    # red at/above this
# Rate-limit hygiene: the menu bar refreshes every minute, but we only actually
# CALL the endpoint when the cache is older than FETCH_TTL. On a 429 we back off
# for BACKOFF_429 (or the server's Retry-After) and keep serving cached numbers.
FETCH_TTL      = 600   # seconds between real fetches (10 min → ~6 calls/hour)
FETCH_JITTER   = 90    # ± random seconds so we don't sync with Claude Code's calls
BACKOFF_429    = 1800  # seconds to wait after a 429 (30 min) if no Retry-After
# Trend + projection (a small 5-hour-utilization history kept in the cache):
HISTORY_MAX    = 48    # samples to keep (~one per fetch, so ~8h at 10-min TTL)
PROJ_WINDOW    = 5400  # seconds of recent history used to estimate burn rate (90 min)
# ────────────────────────────────────────────────────────────────────────────

# ===== token loading (file first, then keychain) =============================
def _find_key(obj, key):
    """Recursively find a value by key anywhere in nested dict/list."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = _find_key(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_key(v, key)
            if r is not None:
                return r
    return None

def load_token():
    raw = None
    if os.path.exists(CREDS_FILE):
        try:
            with open(CREDS_FILE) as fh:
                raw = fh.read()
        except OSError:
            raw = None
    if not raw:
        try:
            raw = subprocess.run(
                ["security", "find-generic-password", "-s", KEYCHAIN_NAME, "-w"],
                capture_output=True, text=True, timeout=8,
            ).stdout.strip()
        except Exception:
            raw = None
    if not raw:
        return None, None
    try:
        data = json.loads(raw)
    except Exception:
        return None, None
    tok = _find_key(data, "accessToken") or _find_key(data, "access_token")
    exp = _find_key(data, "expiresAt") or _find_key(data, "expires_at")
    return tok, exp

# ===== live plan usage =======================================================
def fetch_live():
    tok, exp = load_token()
    if not tok:
        raise RuntimeError("no token")
    if exp:
        # expiresAt is ms epoch in Claude Code creds
        try:
            exp_s = float(exp) / (1000.0 if float(exp) > 1e12 else 1.0)
            if exp_s < time.time():
                raise RuntimeError("token expired")
        except (TypeError, ValueError):
            pass
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {tok}",
        "anthropic-beta": ANTHROPIC_BETA,
        "anthropic-version": ANTHROPIC_VER,
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    })
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        return json.loads(r.read().decode())

def pct(v):
    """Normalize utilization that may be 0-1 or 0-100 into 0-100."""
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v * 100.0 if v <= 1.0 else v

def window(d):
    """Extract (utilization%, resets_at) from a usage sub-object, tolerantly."""
    if not isinstance(d, dict):
        return None, None
    u = pct(d.get("utilization"))
    if u is None:
        u = pct(_find_key(d, "utilization"))
    r = d.get("resets_at") or d.get("resetsAt") or _find_key(d, "resets_at")
    return u, r

def reset_str(r):
    if not r:
        return ""
    try:
        if isinstance(r, (int, float)):
            dt = datetime.fromtimestamp(r / (1000.0 if r > 1e12 else 1.0), timezone.utc).astimezone()
        else:
            dt = datetime.fromisoformat(str(r).replace("Z", "+00:00")).astimezone()
    except Exception:
        return ""
    delta = dt.timestamp() - time.time()
    if delta <= 0:
        return "resets now"
    h = int(delta // 3600); m = int((delta % 3600) // 60)
    return f"resets in {h}h{m:02d}m" if h else f"resets in {m}m"

# ===== local-logs fallback estimate ==========================================
PRICING = {"opus": {"in": 15.0, "out": 75.0}, "sonnet": {"in": 3.0, "out": 15.0},
           "haiku": {"in": 1.0, "out": 5.0}}
def _mk(model):
    m = (model or "").lower()
    for k in PRICING:
        if k in m:
            return k
    return None
def _cost(model, u):
    k = _mk(model)
    if not k:
        return 0.0
    p = PRICING[k]
    return (u.get("input_tokens", 0) * p["in"]
            + u.get("cache_creation_input_tokens", 0) * p["in"] * 1.25
            + u.get("cache_read_input_tokens", 0) * p["in"] * 0.10
            + u.get("output_tokens", 0) * p["out"]) / 1_000_000

def estimate_local():
    now = time.time()
    five_h_ago = now - 5 * 3600
    cutoff = now - 2 * 86400
    block_cost = 0.0
    block_tok = 0
    seen = set()
    for fp in glob.glob(os.path.join(CLAUDE_DIR, "**", "*.jsonl"), recursive=True):
        try:
            if os.path.getmtime(fp) < cutoff:
                continue
        except OSError:
            continue
        try:
            fh = open(fp)
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("type") != "assistant" or o.get("uuid") in seen:
                    continue
                seen.add(o.get("uuid"))
                msg = o.get("message", {}); u = msg.get("usage") or {}
                ts_raw = o.get("timestamp")
                if not u or not ts_raw:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).timestamp()
                except Exception:
                    continue
                if ts >= five_h_ago:
                    block_cost += _cost(msg.get("model", ""), u)
                    block_tok += (u.get("input_tokens", 0) + u.get("output_tokens", 0)
                                  + u.get("cache_creation_input_tokens", 0)
                                  + u.get("cache_read_input_tokens", 0))
    return block_tok, block_cost

def fmt_tok(n):
    if n >= 1_000_000: return f"{n/1_000_000:.2f}M"
    if n >= 1_000: return f"{n/1_000:.1f}K"
    return str(int(n))

# ===== cache =================================================================
def save_cache(d):
    # NB: caller sets d["_ts"] only on a SUCCESSFUL fetch. Persisting a backoff
    # must preserve the original _ts so "updated Xm ago" stays truthful.
    try:
        with open(CACHE_FILE, "w") as fh:
            json.dump(d, fh)
    except OSError:
        pass
def load_cache():
    try:
        with open(CACHE_FILE) as fh:
            return json.load(fh)
    except Exception:
        return None

def color_for(p):
    """Dropdown rows: full green/orange/red (readable on the solid popover)."""
    if p is None: return ""
    if p >= CRIT_PCT: return " color=red"
    if p >= WARN_PCT: return " color=orange"
    return " color=green"

def title_color(p):
    """Menu-bar title: default color until it matters, then alert.
    Default = max contrast on the translucent menu bar (adapts light/dark)."""
    if p is None: return ""
    if p >= CRIT_PCT: return " color=red"
    if p >= WARN_PCT: return " color=orange"
    return ""

BAR_SEGMENTS = 5
def mini_bar(p):
    """Render a unicode mini progress bar for a 0-100 percentage."""
    if p is None:
        return "▱" * BAR_SEGMENTS
    filled = int(round(max(0.0, min(100.0, p)) / 100.0 * BAR_SEGMENTS))
    return "▰" * filled + "▱" * (BAR_SEGMENTS - filled)

def normalize(live):
    """Flatten the /usage response into the cache shape we render from."""
    five_u, five_r = window(live.get("five_hour"))
    week_u, week_r = window(live.get("seven_day"))
    opus_u, opus_r = window(live.get("seven_day_opus"))
    extra = {}
    for k, v in live.items():
        if k in ("five_hour", "seven_day", "seven_day_opus"):
            continue
        u, r = window(v)
        if u is not None:
            extra[k] = [u, r]
    return {"five": five_u, "five_r": five_r, "week": week_u, "week_r": week_r,
            "opus": opus_u, "opus_r": opus_r, "extra": extra}

def get_data():
    """Return (data, fetched_now, err). Only calls the API when the cache is
    stale AND we're not in a 429 backoff window. Otherwise serves cache."""
    cache = load_cache() or {}
    now = time.time()
    age = now - cache.get("_ts", 0)
    have_cache = cache.get("five") is not None or cache.get("week") is not None
    ttl = FETCH_TTL + random.uniform(-FETCH_JITTER, FETCH_JITTER)

    # Respect any active backoff, and skip fetch if cache is still fresh.
    if now < cache.get("backoff_until", 0) or (have_cache and age < ttl):
        return cache, False, None

    try:
        data = normalize(fetch_live())
        data["_ts"] = now
        data["backoff_until"] = 0
        # Carry the trend history forward and append this sample.
        hist = cache.get("history", [])
        if data.get("five") is not None:
            hist = (hist + [[now, round(data["five"], 1)]])[-HISTORY_MAX:]
        data["history"] = hist
        save_cache(data)
        return data, True, None
    except urllib.error.HTTPError as e:
        if e.code == 429:
            ra = e.headers.get("Retry-After") if e.headers else None
            try:
                wait = float(ra)
            except (TypeError, ValueError):
                wait = BACKOFF_429
            cache["backoff_until"] = now + max(wait, 60)
            save_cache(cache)  # keep last-good values, just delay next fetch
            return cache, False, f"429 (backing off {int(max(wait,60)/60)}m)"
        cache["_err"] = str(e)
        return cache, False, str(e)
    except Exception as e:
        return cache, False, str(e)

# ===== trend + projection ====================================================
SPARK = "▁▂▃▄▅▆▇█"
def sparkline(history):
    """Fixed 0-100% sparkline of the 5h-utilization samples."""
    vals = [u for _, u in history if u is not None]
    if not vals:
        return ""
    out = ""
    for v in vals:
        v = max(0.0, min(100.0, v))
        out += SPARK[int(v / 100.0 * (len(SPARK) - 1))]
    return out

def fmt_dur(secs):
    secs = int(max(0, secs))
    h, m = secs // 3600, (secs % 3600) // 60
    return f"{h}h{m:02d}m" if h else f"{m}m"

def project(history, current, reset_iso):
    """Estimate time-to-5h-cap from recent burn rate. Returns a display string.
    Compares against the window reset so we don't warn about a cap you'll
    never reach before the window clears."""
    pts = [(t, u) for t, u in (history or []) if u is not None]
    if len(pts) < 2:
        return None, "gathering trend… (a few more samples)"
    now = time.time()
    recent = [p for p in pts if now - p[0] <= PROJ_WINDOW]
    if len(recent) < 2:
        recent = pts[-2:]
    (t0, u0), (t1, u1) = recent[0], recent[-1]
    dt = t1 - t0
    if dt <= 0:
        return None, None
    rate = (u1 - u0) / dt  # %/sec
    if current is None:
        current = u1
    if rate <= 0:
        return None, "5h usage steady — not climbing"
    secs_to_cap = (100.0 - current) / rate
    # how long until the window resets on its own?
    secs_to_reset = None
    if reset_iso:
        try:
            if isinstance(reset_iso, (int, float)):
                rt = reset_iso / (1000.0 if reset_iso > 1e12 else 1.0)
            else:
                rt = datetime.fromisoformat(str(reset_iso).replace("Z", "+00:00")).timestamp()
            secs_to_reset = rt - now
        except Exception:
            secs_to_reset = None
    if secs_to_reset is not None and secs_to_cap > secs_to_reset:
        return None, f"resets in {fmt_dur(secs_to_reset)} before cap — you're fine"
    crit = secs_to_cap <= 1800  # < 30 min
    return crit, f"~{fmt_dur(secs_to_cap)} to 5h cap at current rate"

# ===== render ================================================================
def main():
    data, fetched, err = get_data()
    have = data.get("five") is not None or data.get("week") is not None

    if have:
        five_u, five_r = data.get("five"), data.get("five_r")
        week_u, week_r = data.get("week"), data.get("week_r")
        opus_u, opus_r = data.get("opus"), data.get("opus_r")

        # Menu bar shows only the 5-hour window; weekly lives in the dropdown.
        headline_pct = five_u if five_u is not None else (week_u or 0)
        print(f"{mini_bar(headline_pct)} {headline_pct:.0f}% | font=Menlo size=13{title_color(headline_pct)}")
        print("---")
        age_m = int((time.time() - data.get("_ts", 0)) / 60)
        freshness = "live" if fetched else f"updated {age_m}m ago"
        print(f"Claude plan limits ({freshness}) | size=11 color=gray")
        if five_u is not None:
            print(f"5-hour window:  {five_u:5.1f}%   {reset_str(five_r)} | font=Menlo{color_for(five_u)}")
            spark = sparkline(data.get("history", []))
            if spark:
                print(f"  trend (recent): {spark} | font=Menlo size=12")
            crit, proj = project(data.get("history", []), five_u, five_r)
            if proj:
                print(f"  {proj} | font=Menlo size=11{' color=orange' if crit else ' color=gray'}")
        if week_u is not None:
            print(f"Weekly (all):   {week_u:5.1f}%   {reset_str(week_r)} | font=Menlo{color_for(week_u)}")
        if opus_u is not None:
            print(f"Weekly (Opus):  {opus_u:5.1f}%   {reset_str(opus_r)} | font=Menlo{color_for(opus_u)}")
        for k, (u, r) in (data.get("extra") or {}).items():
            print(f"{k:<14} {u:5.1f}%   {reset_str(r)} | font=Menlo{color_for(u)}")
        if err and "429" in err:
            print(f"(rate-limited — {err}; showing cached) | size=10 color=gray")
    else:
        # No usable cache yet → local estimate.
        block_tok, block_cost = estimate_local()
        print(f"▱▱▱▱▱ ⚠ ~${block_cost:.0f} | font=Menlo size=13")
        print("---")
        print("⚠ Live plan limits unavailable | size=11 color=orange")
        print(f"Reason: {err or 'no data yet'} | size=10 color=gray")
        print("Showing local estimate instead | size=10 color=gray")
        print("---")
        print(f"Last 5h (est): {fmt_tok(block_tok)} tok · ≈${block_cost:.2f} | font=Menlo")
        print("---")
        print("Tip: open Claude Code once to refresh token | size=10 color=gray")

    print("---")
    print("Force refresh now | bash='/bin/rm' param1=-f param2=" + CACHE_FILE + " terminal=false refresh=true")
    print("Open /usage in Claude Code for official view | size=10 color=gray")
    print("Refresh display | refresh=true")

if __name__ == "__main__":
    main()
