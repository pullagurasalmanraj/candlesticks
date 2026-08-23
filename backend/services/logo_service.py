# services/logo_service.py
# ================================================================
#  Resolves company logo domains for NSE/BSE symbols dynamically.
#
#  Flow:
#  1. Early reject      → options/futures/non-equity symbols → None instantly
#  2. Short Acronyms    → minimal 5-item override dict for 2-letter acronyms
#  3. Redis cache       → instant
#  4. DB cache (stock_logos) → persistent self-learning store
#  5. Clearbit Autocomplete → dynamic corporate domain API
#  6. logo.dev Search   → fallback dynamic company search
#  7. Cache result      → DB + Redis for future instant lookup
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
REDIS_NULL_TTL    = 1 * 24 * 3600   # 1 day  for confirmed-null
REDIS_NULL_MARKER = "__NULL__"       # sentinel stored when domain is confirmed missing

# ── Minimal essential overrides for short 2-3 letter acronym collisions ─────
DOMAIN_OVERRIDES = {
    "ITC": "itcportal.com",
    "LT": "larsentoubro.com",
    "MM": "mahindra.com",
    "VBL": "varunpepsi.com",
    "HAL": "hal-india.co.in",
}


# ── Equity-only guard ─────────────────────────────────────────────
_OPTION_RE  = re.compile(r"\d+\s*(CE|PE)\b", re.IGNORECASE)
_FUTURE_RE  = re.compile(r"\d{2}[A-Z]{3}FUT$", re.IGNORECASE)

def _is_equity_symbol(symbol: str) -> bool:
    s = symbol.strip().upper()
    if " " in s:
        return False
    if _OPTION_RE.search(s):
        return False
    if _FUTURE_RE.search(s):
        return False
    if len(s) > 20:
        return False
    if s in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "NIFTY50", "NIFTYNXT50"):
        return False
    return True


# ── Build symbol → company name map from instruments file ─────────
_NAME_CACHE: dict = {}

def _build_name_cache():
    global _NAME_CACHE
    if _NAME_CACHE:
        return
    inst_path = os.path.join(BASE_DIR, "upstox_instruments.json.gz")
    if not os.path.exists(inst_path):
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
    except Exception as e:
        print("[WARN] Failed to build logo name cache:", e)


def _get_company_name(symbol: str) -> str | None:
    _build_name_cache()
    return _NAME_CACHE.get(symbol.upper().strip())


# ── Smart Company Name Sanitizer for Search APIs ─────────────────
def _clean_company_name_for_search(company_name: str | None, symbol: str) -> str:
    if not company_name:
        return symbol
    n = company_name.upper()
    # Remove entity designations
    n = re.sub(
        r"\b(LIMITED|LTD|LABORATORIES|LABS|CORPORATION|CORP|INDIA|INFRASTRUCTURE|ENTERPRISES|HOLDINGS|SERVICES|FINANCIAL|PLC|INC)\b",
        "",
        n,
        flags=re.IGNORECASE,
    )
    n = re.sub(r"[^A-Z0-9\s]", " ", n)
    n = " ".join(n.split()).strip()
    return n if len(n) >= 2 else symbol


# ── Search API Adapters ──────────────────────────────────────────
def _search_clearbit_domain(query: str) -> str | None:
    try:
        url = f"https://autocomplete.clearbit.com/v1/companies/suggest?query={requests.utils.quote(query)}"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        if r.status_code == 200:
            res = r.json()
            if res and res[0].get("domain"):
                domain = res[0].get("domain")
                if not domain.endswith(".io"):
                    return domain
    except Exception:
        pass
    return None


def _search_logo_dev(query: str) -> str | None:
    try:
        r = requests.get(
            "https://api.logo.dev/search",
            params={"q": query},
            headers={"Authorization": f"Bearer {LOGO_DEV_SECRET}"},
            timeout=5,
        )
        if r.status_code == 200:
            results = r.json()
            if results and results[0].get("domain"):
                return results[0].get("domain")
    except Exception:
        pass
    return None


def _resolve_domain_dynamically(sym: str, company_name: str | None) -> str | None:
    clean_q = _clean_company_name_for_search(company_name, sym)

    # 1. Clearbit Autocomplete Engine
    domain = _search_clearbit_domain(clean_q)
    if domain:
        return domain

    # 2. logo.dev search with cleaned company name
    domain = _search_logo_dev(clean_q)
    if domain:
        return domain

    # 3. Fallback: logo.dev with "India"
    domain = _search_logo_dev(f"{clean_q} India")
    if domain:
        return domain

    # 4. Fallback: logo.dev search with raw symbol
    return _search_logo_dev(sym)


# ── Redis helpers ─────────────────────────────────────────────────
def _redis_get(symbol: str) -> str | None:
    if not REDIS_ENABLED or not redis_client:
        return None
    try:
        return redis_client.get(f"logo:{symbol}")
    except Exception:
        return None


def _redis_set(symbol: str, domain: str | None):
    if not REDIS_ENABLED or not redis_client:
        return
    try:
        if domain:
            redis_client.setex(f"logo:{symbol}", REDIS_TTL_SEC, domain)
        else:
            redis_client.setex(f"logo:{symbol}", REDIS_NULL_TTL, REDIS_NULL_MARKER)
    except Exception:
        pass


# ── DB helpers ────────────────────────────────────────────────────
def _db_get(symbol: str) -> str | None:
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT domain FROM stock_logos WHERE symbol=%s", (symbol,))
                row = cur.fetchone()
                if row is None:
                    return None
                return row["domain"] or ""
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
        print(f"[WARN] logo DB upsert failed for {symbol}:", e)


# ── Main resolver ─────────────────────────────────────────────────
def resolve_logo_domain(symbol: str) -> str | None:
    sym = symbol.upper().strip()

    if not _is_equity_symbol(sym):
        return None

    # Check minimal overrides first
    if sym in DOMAIN_OVERRIDES:
        domain = DOMAIN_OVERRIDES[sym]
        _db_upsert(sym, domain)
        _redis_set(sym, domain)
        return domain

    # 1. Redis cache
    cached = _redis_get(sym)
    if cached is not None:
        return None if cached == REDIS_NULL_MARKER else cached

    # 2. DB cache
    db_val = _db_get(sym)
    if db_val is not None:
        domain = db_val if db_val else None
        _redis_set(sym, domain)
        return domain

    # 3. Dynamic Multi-Source Search (Clearbit + logo.dev)
    company_name = _get_company_name(sym)
    domain       = _resolve_domain_dynamically(sym, company_name)

    # 4. Save result permanently in DB + Redis
    _db_upsert(sym, domain, company_name)
    _redis_set(sym, domain)

    return domain


# ── Batch resolver (used by /api/logo/batch) ──────────────────────
def resolve_logos_batch(symbols: list[str]) -> dict[str, str | None]:
    result   = {}
    to_fetch = []

    for raw in symbols:
        sym = raw.upper().strip()

        if not _is_equity_symbol(sym):
            result[sym] = None
            continue

        if sym in DOMAIN_OVERRIDES:
            domain = DOMAIN_OVERRIDES[sym]
            _db_upsert(sym, domain)
            _redis_set(sym, domain)
            result[sym] = domain
            continue

        cached = _redis_get(sym)
        if cached is not None:
            result[sym] = None if cached == REDIS_NULL_MARKER else cached
            continue

        db_val = _db_get(sym)
        if db_val is not None:
            domain = db_val if db_val else None
            _redis_set(sym, domain)
            result[sym] = domain
            continue

        to_fetch.append(sym)

    for sym in to_fetch:
        company_name = _get_company_name(sym)
        domain       = _resolve_domain_dynamically(sym, company_name)
        _db_upsert(sym, domain, company_name)
        _redis_set(sym, domain)
        result[sym] = domain

    return result
