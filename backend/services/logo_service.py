# services/logo_service.py
# ================================================================
#  Resolves company logo domains for NSE/BSE symbols.
#
#  Flow:
#  1. Early reject    → options/futures/non-equity symbols → None instantly
#  2. Redis cache     → instant
#  3. DB cache        → fast
#  4. logo.dev search → resolves by company name
#  5. Cache result    → Redis + DB for 7 days
#                       None result cached for 1 day (prevents repeat calls)
# ================================================================
import os, json, re, gzip
import requests
from datetime import datetime, timezone

from config     import BASE_DIR
from db         import get_db_conn
from extensions import redis_client, REDIS_ENABLED

LOGO_DEV_KEY      = os.getenv("LOGO_DEV_KEY",    "pk_Ix0rU8q7QveZL0z2Ud9JqA")
LOGO_DEV_SECRET   = os.getenv("LOGO_DEV_SECRET", "sk_Ta_5zMQ1RGGWlNMsKvXuWA")
REDIS_TTL_SEC     = 7 * 24 * 3600   # 7 days for resolved domains
REDIS_NULL_TTL    = 1 * 24 * 3600   # 1 day  for confirmed-null (prevents repeat API calls)
REDIS_NULL_MARKER = "__NULL__"       # sentinel stored when domain is confirmed missing


# ── Equity-only guard ─────────────────────────────────────────────
# Options look like:  "TCS 2120 CE 28 APR 26"
# Futures look like:  "RELIANCE26MARFUT"
# AMC/bond symbols:   often contain digits mid-string or are very long
# Pure equity:        "TCS", "RELIANCE", "HDFCBANK" — uppercase letters only, ≤20 chars

_OPTION_RE  = re.compile(r"\d+\s*(CE|PE)\b", re.IGNORECASE)
_FUTURE_RE  = re.compile(r"\d{2}[A-Z]{3}FUT$", re.IGNORECASE)
_DIGIT_MID  = re.compile(r"[A-Z]\d")   # letter followed by digit mid-symbol (e.g. NIFTY50)

def _is_equity_symbol(symbol: str) -> bool:
    """
    Returns True only for plain equity symbols like TCS, RELIANCE, HDFCBANK.
    Rejects options, futures, indices, ETFs with digits, and long derivative names.
    """
    s = symbol.strip().upper()

    # Reject if contains space — options/futures always have spaces
    if " " in s:
        return False

    # Reject known option/future patterns
    if _OPTION_RE.search(s):
        return False
    if _FUTURE_RE.search(s):
        return False

    # Reject if too long (derivatives tend to be long)
    if len(s) > 20:
        return False

    # Reject index symbols
    if s in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX",
             "NIFTY50", "NIFTYNXT50"):
        return False

    # Allow — plain equity
    return True


# ── Build symbol → company name map from instruments file ─────────
_NAME_CACHE: dict = {}

def _build_name_cache():
    global _NAME_CACHE
    if _NAME_CACHE:
        return
    inst_path = os.path.join(BASE_DIR, "upstox_instruments.json.gz")
    if not os.path.exists(inst_path):
        print("⚠️  Instruments file missing — logo name cache empty")
        return
    try:
        with gzip.open(inst_path, "rt", encoding="utf-8") as f:
            instruments = json.load(f)
        for i in instruments:
            sym  = (i.get("trading_symbol") or i.get("symbol") or "").upper().strip()
            name = (i.get("name") or i.get("company_name") or "").strip()
            seg  = (i.get("segment") or "").upper()
            if sym and name and seg in ("NSE_EQ", "BSE_EQ") and sym not in _NAME_CACHE:
                _NAME_CACHE[sym] = name
        print(f"📋 Logo name cache built: {len(_NAME_CACHE)} symbols")
    except Exception as e:
        print("⚠️  Failed to build logo name cache:", e)


def _get_company_name(symbol: str) -> str | None:
    _build_name_cache()
    return _NAME_CACHE.get(symbol.upper().strip())


# ── logo.dev search API ───────────────────────────────────────────
def _search_logo_dev(query: str) -> str | None:
    try:
        r = requests.get(
            "https://api.logo.dev/search",
            params={"q": query},
            headers={"Authorization": f"Bearer {LOGO_DEV_SECRET}"},
            timeout=5,
        )
        if r.status_code != 200:
            return None
        results = r.json()
        if not results:
            return None
        domain = results[0].get("domain")
        return domain or None
    except Exception:
        return None


# ── Redis helpers ─────────────────────────────────────────────────
def _redis_get(symbol: str) -> str | None:
    """Returns cached domain, REDIS_NULL_MARKER if confirmed null, or None if uncached."""
    if not REDIS_ENABLED or not redis_client:
        return None
    try:
        return redis_client.get(f"logo:{symbol}")
    except Exception:
        return None


def _redis_set(symbol: str, domain: str | None):
    """Cache domain or null marker."""
    if not REDIS_ENABLED or not redis_client:
        return
    try:
        if domain:
            redis_client.setex(f"logo:{symbol}", REDIS_TTL_SEC, domain)
        else:
            # Cache the null result so we don't hit logo.dev again for 1 day
            redis_client.setex(f"logo:{symbol}", REDIS_NULL_TTL, REDIS_NULL_MARKER)
    except Exception:
        pass


# ── DB helpers ────────────────────────────────────────────────────
def _db_get(symbol: str) -> str | None:
    """Returns domain string, empty string if confirmed null, or None if not in DB."""
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT domain FROM stock_logos WHERE symbol=%s",
                    (symbol,)
                )
                row = cur.fetchone()
                if row is None:
                    return None          # not in DB at all
                return row[0] or ""     # empty string = confirmed null
    except Exception:
        return None


def _db_upsert(symbol: str, domain: str | None, name: str | None = None):
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO stock_logos (symbol, domain, company_name, resolved_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (symbol) DO UPDATE SET
                        domain      = EXCLUDED.domain,
                        resolved_at = EXCLUDED.resolved_at
                """, (symbol, domain, name, datetime.now(timezone.utc)))
    except Exception as e:
        print(f"⚠️  logo DB upsert failed for {symbol}:", e)


# ── Main resolver ─────────────────────────────────────────────────
def resolve_logo_domain(symbol: str) -> str | None:
    """
    Returns the logo.dev domain for an equity symbol, or None.
    Non-equity symbols (options, futures, indices) return None immediately.
    Null results are cached for 1 day to prevent repeat API calls.
    """
    sym = symbol.upper().strip()

    # Fast reject — options/futures/non-equity never have logos
    if not _is_equity_symbol(sym):
        return None

    # 1. Redis cache — check for both domain and confirmed-null
    cached = _redis_get(sym)
    if cached is not None:
        return None if cached == REDIS_NULL_MARKER else cached

    # 2. DB cache
    db_val = _db_get(sym)
    if db_val is not None:
        # db_val is "" for confirmed null, or a domain string
        domain = db_val if db_val else None
        _redis_set(sym, domain)
        return domain

    # 3. logo.dev search API using company name
    company_name = _get_company_name(sym)
    domain       = None

    if company_name:
        domain = _search_logo_dev(company_name)

    # Fallback: search by symbol itself
    if not domain:
        domain = _search_logo_dev(sym)

    # 4. Persist result (None stored as empty string in DB)
    _db_upsert(sym, domain, company_name)
    _redis_set(sym, domain)

    return domain


# ── Batch resolver (used by /api/logo/batch) ──────────────────────
def resolve_logos_batch(symbols: list[str]) -> dict[str, str | None]:
    """
    Resolve multiple symbols in one call.
    Returns {symbol: domain_or_None}.
    Skips non-equity symbols without any API call.
    Checks Redis/DB for all before making any logo.dev calls.
    """
    result   = {}
    to_fetch = []   # symbols that need a logo.dev API call

    for raw in symbols:
        sym = raw.upper().strip()

        # Instant reject for non-equity
        if not _is_equity_symbol(sym):
            result[sym] = None
            continue

        # Redis hit
        cached = _redis_get(sym)
        if cached is not None:
            result[sym] = None if cached == REDIS_NULL_MARKER else cached
            continue

        # DB hit
        db_val = _db_get(sym)
        if db_val is not None:
            domain = db_val if db_val else None
            _redis_set(sym, domain)
            result[sym] = domain
            continue

        to_fetch.append(sym)

    # Only hit logo.dev for genuinely uncached equity symbols
    for sym in to_fetch:
        company_name = _get_company_name(sym)
        domain       = None

        if company_name:
            domain = _search_logo_dev(company_name)
        if not domain:
            domain = _search_logo_dev(sym)

        _db_upsert(sym, domain, company_name)
        _redis_set(sym, domain)
        result[sym] = domain

    return result
