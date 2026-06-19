#!/usr/bin/env python3
"""News Desk agents backend.

Three LLM "agents" (Google Gemini with the google_search grounding tool) that fire when the
dashboard's News button is clicked. Each agent researches the most relevant items for its
category and returns them as JSON the front-end renders.

  GET /api/health          -> {ok, engine, model, has_key}
  GET /api/news/macro      -> {ok, category, items:[...]}
  GET /api/news/gov        -> {ok, category, items:[...]}  (US + CA government sources only)
  GET /api/news/social     -> {ok, category, items:[...]}

Config via environment:
  GEMINI_API_KEY       (required)  Google Gemini API key (free: https://aistudio.google.com/apikey).
  GEMINI_MODEL         (optional)  Model id. Default: gemini-2.5-flash.
  PORT / NEWS_PORT     (optional)  Port to listen on. PORT wins (Cloud Run/Render set it). Default: 8181.
  NEWS_HOST            (optional)  Bind address. Default: 127.0.0.1 (use 0.0.0.0 in a container).
  NEWS_MAX_ITEMS       (optional)  Max items per feed. Default: 8.
  NEWS_ALLOWED_ORIGIN  (optional)  CORS allow-list (comma-separated origins, or *). Default: *.
  NEWS_TOKEN           (optional)  If set, requests must send it via X-News-Token header or ?token=.
  NEWS_RATE_LIMIT      (optional)  Max requests per IP per window. Default: 30.
  NEWS_RATE_WINDOW     (optional)  Rate-limit window in seconds. Default: 60.

No secrets are stored in this file; the key is read from the environment at runtime.
"""

import json
import os
import re
import sys
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import httpx

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
# PORT (Cloud Run / Render convention) wins over NEWS_PORT; fall back to 8181 for local dev.
PORT = int(os.environ.get("PORT", os.environ.get("NEWS_PORT", "8181")))
HOST = os.environ.get("NEWS_HOST", "127.0.0.1")
MAX_ITEMS = int(os.environ.get("NEWS_MAX_ITEMS", "8"))
REQUEST_TIMEOUT = 180.0

# CORS: comma-separated allow-list of origins (or "*"). Default "*" keeps local dev working;
# the hosted deployment sets this to the Pages origin (e.g. https://will-smith12.github.io).
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("NEWS_ALLOWED_ORIGIN", "*").split(",") if o.strip()]
# Optional shared access token. When set, /api/news/* requires it (X-News-Token header or ?token=).
NEWS_TOKEN = os.environ.get("NEWS_TOKEN", "").strip()
# Simple per-IP fixed-window rate limit (per process instance).
RATE_LIMIT = int(os.environ.get("NEWS_RATE_LIMIT", "30"))
RATE_WINDOW = float(os.environ.get("NEWS_RATE_WINDOW", "60"))

# Official US + Canadian government domains the gov agent is restricted to.
GOV_DOMAINS = [
    "federalreserve.gov", "bls.gov", "bea.gov", "treasury.gov", "whitehouse.gov",
    "sec.gov", "congress.gov", "commerce.gov", "census.gov",
    "bankofcanada.ca", "statcan.gc.ca", "canada.ca", "fin.gc.ca", "parl.ca",
]

# Social platforms the social agent draws chatter from.
SOCIAL_DOMAINS = [
    "x.com", "twitter.com", "reddit.com", "linkedin.com", "stocktwits.com", "threads.net",
]

# Curated, reputable macro Substacks / blogs the social agent may draw from. Matching is by host
# suffix, so custom domains and *.substack.com subdomains both work.
CURATED_PUBLICATION_DOMAINS = [
    # Canada
    "philip635.substack.com", "philsmith.substack.com",  # Philip's Economic Commentary (ex-StatCan)
    "thelooniehour.substack.com",                          # The Loonie Hour (BoC + housing)
    "stevesaretsky.com", "stevesaretsky.substack.com", "vancouvermarket.ca",  # Steve Saretsky
    "missingmiddle.ca",                                    # Mike Moffatt — The Missing Middle
    # Canadian bank chief-economist portals (Porter/Caranci/Tal/Shenfeld/Holt — their primary outlet)
    "economics.bmo.com", "economics.td.com", "cibccm.com", "scotiabank.com",
    # US / global
    "noahpinion.substack.com", "noahpinion.blog",          # Noah Smith
    "theovershoot.co",                                     # Matthew Klein
    "calculatedrisk.substack.com", "calculatedriskblog.com",  # Bill McBride
    "claudiasahm.substack.com",                            # Claudia Sahm — Stay-At-Home Macro
    "johnhcochrane.substack.com", "grumpy-economist.com",  # John Cochrane — The Grumpy Economist
    "pragcap.com", "disciplinefunds.com",                  # Cullen Roche — Pragmatic Capitalism
    "newsletter.doomberg.com", "doomberg.com",             # Doomberg
    "moneyandmacro.substack.com",                          # Money & Macro
    "netinterest.co",                                      # Marc Rubinstein — Net Interest
    "mohamedelerian.substack.com",                         # Mohamed El-Erian
    # Curated people's own blogs / publications (primary sources, not third-party coverage)
    "ritholtz.com",                                        # Barry Ritholtz — The Big Picture
    "biancoresearch.com",                                  # Jim Bianco
    "charliebilello.com",                                  # Charlie Bilello
]

# Curated people whose own X / LinkedIn posts are allowed (best-effort; these sites rarely surface
# via search grounding, but when they do we accept the named accounts). Lowercase handles.
CURATED_HANDLES = [
    # US / global
    "elerianm", "nouriel", "justinwolfers", "claudia_sahm", "jasonfurman", "lizannsonders",
    "charliebilello", "ritholtz", "thestalwart", "lisaabramowicz1", "nicktimiraos",
    "biancoresearch", "gregdaco", "c_barraud",
    # Canada
    "porter_bmo", "beatacaranci", "bental66", "ashenfeld", "derekholtscotia", "trevortombe",
    "mikepmoffatt", "kevincarmichael",
]


# ── Agent definitions ───────────────────────────────────────────────────────
def _common_rules(shape: str) -> str:
    return (
        f"Find the {MAX_ITEMS} most relevant and most recent items. Cover BOTH the United "
        "States (region \"us\") and Canada (region \"ca\"); aim for a roughly even mix.\n"
        "Return ONLY a single JSON array (no prose, no markdown outside the code fence) "
        "wrapped in a ```json code fence. Each element must be an object with exactly these "
        f"keys:\n{shape}\n"
        "Use concise, factual text. 'time' is a short human recency label like \"2h ago\", "
        "\"today\", or a date. 'iso' is the SAME moment as an absolute ISO 8601 UTC timestamp "
        "(e.g. \"2026-06-17T14:30:00Z\") giving your best estimate of when the item was "
        "published or released — this is used to sort the feed chronologically, so always "
        "provide it. 'url' is the source link."
    )


AGENTS = {
    "macro": {
        "gov_only": False,
        "system": (
            "You are a macro markets news editor for a US-Canada macroeconomics dashboard. "
            "Surface the most important, market-moving macro headlines from roughly the last "
            "48-72 hours.\n"
            "PREFERRED SOURCES (favor these, in order):\n"
            "  - Wires & breaking (free, fast): Reuters, Associated Press, MarketWatch, "
            "Yahoo Finance.\n"
            "  - Business flagships: CNBC, Bloomberg, Wall Street Journal, Financial Times, "
            "Barron's, Axios Markets.\n"
            "  - Canada-focused (use these so the feed is NOT US-dominated): BNN Bloomberg, "
            "Financial Post, The Globe and Mail (Report on Business), CBC Business, CTV Business.\n"
            "  - Data/rates/FX/commodities: Trading Economics, Investing.com.\n"
            "BEATS TO COVER (spread across them; do not stack multiple stories on one print): "
            "inflation/CPI, jobs/employment, GDP & growth, central banks (Federal Reserve & Bank "
            "of Canada), interest rates & bond yields, trade & tariffs, housing, the consumer, and "
            "energy/commodities (especially relevant for Canada).\n"
            "RULES: de-duplicate — never include the same story from two outlets; pick the best "
            "single report. Favor reported news and data reactions over opinion/promotional pieces. "
            "Cite the NEWS OUTLET that reported the story (the 'source' and 'url' must be a media "
            "outlet, e.g. Reuters, CNBC, BNN, MarketWatch). Do NOT link primary government or "
            "statistical-agency release pages (bls.gov, statcan.gc.ca, federalreserve.gov, etc.) — "
            "those belong in the separate Government feed; here, link the outlet that covered them. "
            "Paywalled outlets are fine for headline coverage. Keep a roughly even US/Canada mix.\n\n"
            + _common_rules(
                '{"region":"us"|"ca", "source":"<short outlet name e.g. CNBC, BNN, MarketWatch, '
                'Reuters>", "headline":"<concise headline>", "dek":"<one-sentence summary>", '
                '"time":"<recency>", "iso":"<ISO 8601 UTC timestamp>", "url":"<link>"}'
            )
        ),
    },
    "gov": {
        "gov_only": True,
        "system": (
            "You are a government-releases editor. Use ONLY official United States and Canadian "
            "government sources, and every 'url' MUST be on an official government domain such as "
            "federalreserve.gov, bls.gov, bea.gov, treasury.gov, whitehouse.gov, census.gov, "
            "bankofcanada.ca, statcan.gc.ca, canada.ca, or fin.gc.ca. Do NOT use news outlets or "
            "third-party sites. Surface the newest official data prints and policy actions. For a "
            "data release, fill 'val' with the headline figure and 'prev' with the prior/forecast "
            "value and set 'kind' to \"data\"; for a policy action set 'kind' to \"policy\". Set "
            "'dir' to \"up\", \"down\", or \"flat\" describing how 'val' moved vs 'prev'.\n\n"
            + _common_rules(
                '{"region":"us"|"ca", "agency":"<e.g. Fed, BLS, BEA, Treasury, BoC, StatCan, '
                'Finance>", "kind":"data"|"policy", "headline":"<what was released>", '
                '"sub":"<short detail of the metric>", "val":"<headline value>", '
                '"prev":"<prior or forecast value>", "dir":"up"|"down"|"flat", '
                '"time":"<recency>", "iso":"<ISO 8601 UTC timestamp>", "url":"<official government link>"}'
            )
        ),
    },
    "social": {
        "gov_only": False,
        "social_only": True,
        "system": (
            "You are a curated macro-commentary monitor for a US-Canada macroeconomics dashboard. "
            "Surface RECENT, substantive commentary about macro data, central banks (Fed & Bank of "
            "Canada), inflation, jobs, GDP, rates, bonds, housing, and markets — drawn ONLY from "
            "the curated, reputable voices and publications below. Prefer their newest posts/essays. "
            "Do NOT scour the open internet or pull anonymous/low-quality accounts.\n"
            "CURATED SUBSTACKS / BLOGS (best source — these reliably have public posts):\n"
            "  Canada: Philip's Economic Commentary (philip635.substack.com), The Loonie Hour "
            "(thelooniehour.substack.com — Bank of Canada & housing), Steve Saretsky "
            "(stevesaretsky.com — housing).\n"
            "  US/global: Noahpinion (Noah Smith), The Overshoot (Matthew Klein, theovershoot.co), "
            "Calculated Risk (Bill McBride), Stay-At-Home Macro (Claudia Sahm), The Grumpy Economist "
            "(John Cochrane), Pragmatic Capitalism (Cullen Roche, pragcap.com), Doomberg, Money & "
            "Macro, Net Interest (Marc Rubinstein — banks/credit/central banks).\n"
            "CURATED PEOPLE (also use their own X or LinkedIn posts when available):\n"
            "  US/global: Mohamed El-Erian (@elerianm), Nouriel Roubini (@Nouriel), Justin Wolfers "
            "(@JustinWolfers), Claudia Sahm (@Claudia_Sahm), Jason Furman (@jasonfurman), Liz Ann "
            "Sonders (@LizAnnSonders), Charlie Bilello (@charliebilello), Barry Ritholtz (@ritholtz), "
            "Joe Weisenthal (@TheStalwart), Lisa Abramowicz (@lisaabramowicz1), Nick Timiraos "
            "(@NickTimiraos), Jim Bianco (@biancoresearch), Greg Daco (@GregDaco).\n"
            "  Canada: Douglas Porter/BMO (@Porter_BMO), Beata Caranci/TD (@BeataCaranci), Benjamin "
            "Tal/CIBC (@BenTal66), Avery Shenfeld/CIBC (@AShenfeld), Derek Holt/Scotiabank "
            "(@DerekHoltScotia), Trevor Tombe (@trevortombe), Mike Moffatt (@MikePMoffatt), Kevin "
            "Carmichael (@kevincarmichael).\n"
            "RULES: only the curated voices/publications above — if you can't attribute a post to "
            "one of them, leave it out. CRITICAL: return each author's OWN post/essay/newsletter "
            "(e.g. on their Substack, blog, or X), NOT third-party news articles, interviews, "
            "podcasts, or YouTube videos ABOUT them. Search each named publication/person for their "
            "single most recent macro post (e.g. \"Noahpinion latest\", \"The Loonie Hour latest\", "
            "\"theovershoot.co\", \"Calculated Risk\"). Set 'platform' to where the post actually "
            "lives: \"Substack\", \"Blog\", \"X\", \"LinkedIn\", or \"Medium\" (must match the linked "
            "URL's site). Verify the real author/handle and link to the actual post. Quote or tightly "
            "summarize what they said. De-duplicate (no two items from the same author). BALANCE: "
            "include at least 3 Canada-region items, using the Canadian Substacks above. Skip "
            "promotional, off-topic, or unverifiable posts.\n\n"
            + _common_rules(
                '{"region":"us"|"ca", "handle":"<author name or @handle>", '
                '"platform":"<Substack|Blog|X|LinkedIn|Medium>", "text":"<short quote/summary of the '
                'post>", "time":"<recency>", "iso":"<ISO 8601 UTC timestamp>", "url":"<link to the post>"}'
            )
        ),
    },
}


def _host_is_gov(url: str) -> bool:
    """True if the URL's host is (a subdomain of) an official US/CA government domain."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return any(host == d or host.endswith("." + d) for d in GOV_DOMAINS)


# ── Curated-source allowlist for the social feed ───────────────────────────
# Map a host suffix to a display platform label, so we can normalize 'platform' from the URL.
_HOST_TO_PLATFORM = {
    "x.com": "X", "twitter.com": "X",
    "linkedin.com": "LinkedIn", "lnkd.in": "LinkedIn",
    "medium.com": "Medium",
    "substack.com": "Substack",
}


def _host_of(url: str) -> str:
    try:
        return (urlparse(url or "").hostname or "").lower()
    except Exception:
        return ""


def _host_matches(host: str, domain: str) -> bool:
    """True if host equals domain or is a subdomain of it."""
    return host == domain or host.endswith("." + domain)


def _normalize_platform(host: str, label: str) -> str:
    """Pick a sensible display platform from the URL host, falling back to the model's label."""
    for suffix, plat in _HOST_TO_PLATFORM.items():
        if _host_matches(host, suffix):
            return plat
    if host.endswith("substack.com"):
        return "Substack"
    lab = (label or "").strip()
    return lab if lab else "Blog"


def _curated_platform(item: dict):
    """Return a normalized platform for a social item if its URL belongs to a curated publication
    OR a curated person's handle/account; else None. Replaces the old strict 4-platform filter so
    quality stays high (only roster voices) without forcing everything onto Substack."""
    url = item.get("url", "")
    host = _host_of(url)
    if not host:
        return None
    label = str(item.get("platform", ""))

    # 1) Curated Substack / blog publications (host suffix match).
    if any(_host_matches(host, d) for d in CURATED_PUBLICATION_DOMAINS):
        return _normalize_platform(host, label)

    # 2) Curated people on X / LinkedIn — only if the linked account matches a curated handle.
    if _host_matches(host, "x.com") or _host_matches(host, "twitter.com") or \
       _host_matches(host, "linkedin.com") or _host_matches(host, "lnkd.in"):
        hay = (url + " " + str(item.get("handle", ""))).lower()
        if any(("@" + h) in hay or ("/" + h) in hay for h in CURATED_HANDLES):
            return _normalize_platform(host, label)

    return None


# ── Gemini call + parsing ───────────────────────────────────────────────────
def _salvage_objects(text: str, start: int):
    """Collect complete top-level {...} objects from text starting at the first '['.

    Tolerates a truncated final object (dropped) and a model that restarts the array
    (we stop at the first ']' that closes the array, or at end-of-text). Returns a list
    of parsed dicts, or None if nothing parseable was found.
    """
    items = []
    i = start + 1  # past the opening '['
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "]":
            break  # logical end of the array
        if ch != "{":
            i += 1
            continue
        # Walk one object, tracking string state and brace depth.
        depth = 0
        in_str = False
        esc = False
        j = i
        obj_end = -1
        while j < n:
            c = text[j]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        obj_end = j
                        break
            j += 1
        if obj_end == -1:
            break  # object truncated — stop, keep what we have
        chunk = text[i : obj_end + 1]
        try:
            items.append(json.loads(chunk))
        except json.JSONDecodeError:
            pass
        i = obj_end + 1
    return items or None


def _extract_json_array(text: str):
    """Pull a JSON array out of the model's final text.

    Tries (1) a well-formed fenced ```json [...]``` block, then (2) a tolerant scan that
    salvages complete {...} objects from the first '[' onward (handles truncated output
    and a duplicated/restarted array).
    """
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass  # fall through to tolerant salvage
    start = text.find("[")
    if start != -1:
        salvaged = _salvage_objects(text, start)
        if salvaged is not None:
            return salvaged
    raise ValueError("no JSON array found in model response")


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _parse_iso(value) -> datetime:
    """Parse an item's 'iso' timestamp into an aware UTC datetime.

    Tolerates a trailing 'Z', date-only values, and junk (returns the epoch so
    undated items sort to the bottom rather than crashing the sort).
    """
    if not isinstance(value, str) or not value.strip():
        return _EPOCH
    s = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:
            dt = datetime.fromisoformat(s[:10])  # fall back to the date part
        except ValueError:
            return _EPOCH
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _sort_chronologically(items):
    """Return items newest-first by their 'iso' timestamp (stable)."""
    return sorted(
        (d for d in items if isinstance(d, dict)),
        key=lambda d: _parse_iso(d.get("iso")),
        reverse=True,
    )


def _author_key(item: dict) -> str:
    """Normalized identity for a social author, for de-duplication."""
    h = str(item.get("handle", "")).strip().lower().lstrip("@")
    if h:
        return h
    # Fall back to the publication host so two anonymous items from one blog collapse.
    return _host_of(item.get("url", ""))


def _dedup_and_balance_social(items, limit, ca_target=3):
    """De-duplicate by author (keep newest), then select up to `limit` items with a soft Canada
    quota so a single click can't collapse to all-US when Canadian posts are available.

    Input may be in any order; output is newest-first and capped at `limit`."""
    ordered = _sort_chronologically(items)  # newest-first

    # 1) One item per author (first = newest wins).
    seen, deduped = set(), []
    for d in ordered:
        key = _author_key(d)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(d)

    if len(deduped) <= limit:
        return deduped

    # 2) Soft Canada quota: reserve up to ca_target slots for the newest CA items, then fill the
    #    remaining slots with the newest items overall (regardless of region).
    ca = [d for d in deduped if d.get("region") == "ca"]
    reserved = ca[:ca_target]
    reserved_ids = {id(d) for d in reserved}
    fill = [d for d in deduped if id(d) not in reserved_ids]

    selected = reserved + fill[: max(0, limit - len(reserved))]
    return _sort_chronologically(selected)[:limit]


def run_agent(category: str):
    cfg = AGENTS[category]
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {"ok": False, "category": category,
                "error": "GEMINI_API_KEY is not set. Export it and restart the backend."}

    payload = {
        "system_instruction": {"parts": [{"text": cfg["system"]}]},
        "contents": [{
            "role": "user",
            "parts": [{"text": (
                f"Research and return the top {MAX_ITEMS} items now. "
                "Output only the JSON array as instructed."
            )}],
        }],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 8192},
    }
    headers = {
        "x-goog-api-key": api_key,
        "content-type": "application/json",
    }
    url = GEMINI_URL.format(model=DEFAULT_MODEL)

    # Retry transient overload/server errors (free-tier grounding is occasionally flaky).
    RETRY_STATUS = {429, 500, 503}
    resp = None
    for attempt in range(3):
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        except httpx.HTTPError as exc:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            return {"ok": False, "category": category, "error": f"request failed: {exc}"}
        if resp.status_code in RETRY_STATUS and attempt < 2:
            time.sleep(2 * (attempt + 1))
            continue
        break

    if resp.status_code != 200:
        detail = resp.text[:400]
        return {"ok": False, "category": category,
                "error": f"Gemini API {resp.status_code}: {detail}"}

    data = resp.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError):
        return {"ok": False, "category": category,
                "error": "unexpected Gemini response shape", "raw": json.dumps(data)[:600]}

    try:
        items = _extract_json_array(text)
    except (ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "category": category,
                "error": f"could not parse model output: {exc}", "raw": text[:600]}

    if not isinstance(items, list):
        items = []
    # The gov agent is restricted to official US/CA government sources: drop anything else.
    if cfg.get("gov_only"):
        items = [d for d in items if isinstance(d, dict) and _host_is_gov(d.get("url", ""))]
    # The social agent is restricted to a curated roster of reputable macro voices/publications:
    # keep only items whose URL belongs to a curated Substack/blog or a curated person's account,
    # and normalize the platform label from the host.
    if cfg.get("social_only"):
        kept = []
        for d in items:
            if not isinstance(d, dict):
                continue
            plat = _curated_platform(d)
            if plat is None:
                continue
            d["platform"] = plat
            kept.append(d)
        items = kept
        # De-dup by author + soft Canada balance, then cap (this also sorts newest-first).
        items = _dedup_and_balance_social(items, MAX_ITEMS)
        return {"ok": True, "category": category, "items": items}
    # Order newest-first by the model-supplied ISO timestamp, then cap the count.
    items = _sort_chronologically(items)
    items = items[:MAX_ITEMS]
    return {"ok": True, "category": category, "items": items}


# ── HTTP server ─────────────────────────────────────────────────────────────
# Per-IP fixed-window rate limiter (per process). Cloud Run may run several instances, so this is
# a best-effort cap per instance — enough to deter casual abuse of the Gemini quota.
_rate_hits = defaultdict(deque)
_rate_lock = threading.Lock()


def _rate_limited(client_ip: str) -> bool:
    """Return True if this client has exceeded RATE_LIMIT requests within RATE_WINDOW seconds."""
    if RATE_LIMIT <= 0:
        return False
    now = time.monotonic()
    with _rate_lock:
        hits = _rate_hits[client_ip]
        while hits and now - hits[0] > RATE_WINDOW:
            hits.popleft()
        if len(hits) >= RATE_LIMIT:
            return True
        hits.append(now)
        return False


class Handler(BaseHTTPRequestHandler):
    def _cors_origin(self):
        """Pick the Access-Control-Allow-Origin value for this request."""
        if "*" in ALLOWED_ORIGINS:
            return "*"
        origin = self.headers.get("Origin", "")
        if origin and origin in ALLOWED_ORIGINS:
            return origin
        return ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else "*"

    def _send(self, status, body):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", self._cors_origin())
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-News-Token")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _client_ip(self):
        # Honor the proxy header set by Cloud Run / Render, else the socket peer.
        fwd = self.headers.get("X-Forwarded-For", "")
        if fwd:
            return fwd.split(",")[0].strip()
        return self.client_address[0] if self.client_address else "?"

    def _token_ok(self):
        """True if no token is configured, or the request supplied the correct one."""
        if not NEWS_TOKEN:
            return True
        supplied = self.headers.get("X-News-Token", "")
        if not supplied:
            qs = parse_qs(urlparse(self.path).query)
            supplied = (qs.get("token", [""])[0])
        return supplied == NEWS_TOKEN

    def do_OPTIONS(self):  # noqa: N802 - http.server API
        self._send(204, {})

    def do_GET(self):  # noqa: N802 - http.server API
        path = self.path.split("?", 1)[0].rstrip("/")
        if path in ("/api/health", "/api/health".rstrip("/")):
            self._send(200, {
                "ok": True,
                "engine": "gemini",
                "model": DEFAULT_MODEL,
                "has_key": bool(os.environ.get("GEMINI_API_KEY")),
            })
            return
        match = re.fullmatch(r"/api/news/(macro|gov|social)", path)
        if match:
            if not self._token_ok():
                self._send(401, {"ok": False, "error": "missing or invalid token"})
                return
            if _rate_limited(self._client_ip()):
                self._send(429, {"ok": False, "error": "rate limit exceeded, try again shortly"})
                return
            result = run_agent(match.group(1))
            self._send(200, result)
            return
        self._send(404, {"ok": False, "error": "not found"})

    def log_message(self, fmt, *args):
        sys.stderr.write("[news_agents] " + (fmt % args) + "\n")


def main():
    if not os.environ.get("GEMINI_API_KEY"):
        sys.stderr.write(
            "[news_agents] WARNING: GEMINI_API_KEY is not set — endpoints will return errors "
            "until you export it. Get a free key at https://aistudio.google.com/apikey\n"
        )
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    sys.stderr.write(
        f"[news_agents] listening on http://{HOST}:{PORT} (model={DEFAULT_MODEL}, "
        f"cors={','.join(ALLOWED_ORIGINS)}, token={'on' if NEWS_TOKEN else 'off'})\n"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
