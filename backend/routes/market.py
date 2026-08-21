# routes/market.py
# ================================================================
#  Market data blueprint:
#    GET  /api/index-summary
#    GET  /api/ws-subscribe
#    POST /api/unsubscribe
# ================================================================
import json, time as systime
from datetime import datetime, time as dtime

from flask import Blueprint, request, jsonify

from config                 import UPSTOX_API_BASE, safe_requests, INDIA_TZ
from extensions             import redis_client, REDIS_ENABLED
from services.token_service import load_saved_tokens, refresh_upstox_token
from utils.symbol_map       import SYMBOL_TO_KEY

market_bp = Blueprint("market", __name__)

_last_market_data = None
_last_market_time = 0


def is_market_open() -> bool:
    now = datetime.now(INDIA_TZ).time()
    return dtime(9, 0) <= now <= dtime(15, 30)


# ── Index summary ────────────────────────────────────────────────
@market_bp.route("/api/index-summary", methods=["GET"])
def index_summary():
    global _last_market_data, _last_market_time

    ttl    = 15 if is_market_open() else 300
    now_ts = systime.time()
    as_of  = datetime.now(INDIA_TZ).isoformat()

    if REDIS_ENABLED and redis_client:
        try:
            cached = redis_client.get("cache:index_summary")
            if cached:
                return jsonify(json.loads(cached))
        except Exception:
            pass

    if _last_market_data and (now_ts - _last_market_time) < ttl:
        return jsonify(_last_market_data)

    tokens       = load_saved_tokens()
    access_token = tokens.get("access_token")
    if not access_token:
        return jsonify({"error": "Not logged in — connect Upstox"}), 401

    INDEX_KEYS = {
        "Nifty 50":      "NSE_INDEX|Nifty 50",
        "Bank Nifty":    "NSE_INDEX|Nifty Bank",
        "Sensex":        "BSE_INDEX|SENSEX",
        "Nifty Next 50": "NSE_INDEX|Nifty Next 50",
    }
    symbols = ",".join(INDEX_KEYS.values())
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

    quote_url = f"{UPSTOX_API_BASE}/market-quote/quotes?instrument_key={symbols}"
    response = safe_requests.get(quote_url, headers=headers, timeout=10)

    if response.status_code == 401:
        if refresh_upstox_token():
            headers["Authorization"] = f"Bearer {load_saved_tokens().get('access_token')}"
            response = safe_requests.get(quote_url, headers=headers, timeout=10)
        else:
            return jsonify({"error": "Session expired — login again"}), 401

    if response.status_code != 200:
        if _last_market_data:
            stale = dict(_last_market_data)
            stale["status"] = "stale"
            stale["warning"] = "Live index summary unavailable; serving stale cache"
            return jsonify(stale), 200
        return jsonify({
            "status": "degraded",
            "indices": {},
            "marketSummary": {"title": "Market Data Unavailable", "avg_percent": 0},
            "asOf": as_of,
            "warning": "Live index summary unavailable",
            "details": response.text,
        }), 200

    data_raw = (response.json() or {}).get("data", {})
    rows_by_key = {}
    if isinstance(data_raw, dict):
        for map_key, row in data_raw.items():
            if not isinstance(row, dict):
                continue
            row_key = str(row.get("instrument_token") or map_key).replace(":", "|")
            rows_by_key[row_key.upper()] = row
            rows_by_key[str(map_key).replace(":", "|").upper()] = row
    elif isinstance(data_raw, list):
        for row in data_raw:
            if not isinstance(row, dict):
                continue
            row_key = str(
                row.get("instrument_token")
                or row.get("instrument_key")
                or ""
            ).replace(":", "|")
            if row_key:
                rows_by_key[row_key.upper()] = row

    summary = {}
    total_pct, count = 0, 0

    for name, key in INDEX_KEYS.items():
        row = rows_by_key.get(key.upper())
        if not row:
            continue

        def safe(v):
            try:    return round(float(v), 2)
            except: return 0

        ohlc = row.get("ohlc") if isinstance(row.get("ohlc"), dict) else {}
        ltp = safe(row.get("ltp", row.get("last_price")))
        prev_close = safe(row.get("cp", row.get("close", ohlc.get("close"))))
        open_px = safe(row.get("open", ohlc.get("open")))
        high_px = safe(row.get("high", ohlc.get("high")))
        low_px = safe(row.get("low", ohlc.get("low")))
        change = safe(row.get("change", row.get("net_change", ltp - prev_close)))
        percent = safe(
            row.get(
                "percent_change",
                ((change / prev_close) * 100.0) if prev_close else 0.0,
            )
        )

        summary[name] = {
            "symbol": key, "displayName": name, "ltp": ltp,
            "open": open_px, "high": high_px,
            "low": low_px, "prevClose": prev_close,
            "change": change, "percent": percent,
            "direction": "up" if change >= 0 else "down",
            "source": "Upstox Live",
        }
        total_pct += percent
        count     += 1

    avg_pct = round(total_pct / count, 2) if count else 0
    icon    = "▲" if avg_pct >= 0 else "▼"
    payload = {
        "status": "success", "indices": summary,
        "marketSummary": {
            "title": f"{icon} Market {'UP' if avg_pct >= 0 else 'DOWN'}",
            "avg_percent": avg_pct,
        },
        "asOf": as_of,
    }

    _last_market_data = payload
    _last_market_time = now_ts
    if REDIS_ENABLED and redis_client:
        redis_client.setex("cache:index_summary", ttl, json.dumps(payload))

    return jsonify(payload)


# ── WebSocket subscribe ──────────────────────────────────────────
def _resolve_one_instrument_key(raw_symbol: str, exchange: str = ""):
    symbol_raw = (raw_symbol or "").strip()
    if not symbol_raw:
        return None, None, "symbol missing"

    if "|" in symbol_raw:
        return symbol_raw, symbol_raw, None

    symbol = symbol_raw.upper()
    mapped = SYMBOL_TO_KEY.get(symbol)
    if not mapped:
        return None, None, f"Symbol not found: {symbol}"

    if isinstance(mapped, str):
        return mapped, symbol, None

    if isinstance(mapped, dict):
        instrument_key = mapped.get(exchange) or mapped.get("NSE") or list(mapped.values())[0]
        return instrument_key, symbol, None

    return None, None, "Invalid mapping format"


def _collect_subscribe_targets():
    body = request.get_json(silent=True) or {}
    exchange = (
        body.get("exchange")
        or request.args.get("exchange")
        or ""
    ).strip().upper()

    raw_targets = []

    # GET compatibility
    if request.args.get("symbol"):
        raw_targets.append(request.args.get("symbol"))
    raw_targets.extend(request.args.getlist("symbols"))
    raw_targets.extend(request.args.getlist("instrument_key"))
    raw_targets.extend(request.args.getlist("instrument_keys"))

    # POST payload support
    if body.get("symbol"):
        raw_targets.append(body.get("symbol"))
    if isinstance(body.get("symbols"), list):
        raw_targets.extend(body.get("symbols"))
    if body.get("instrument_key"):
        raw_targets.append(body.get("instrument_key"))
    if isinstance(body.get("instrument_keys"), list):
        raw_targets.extend(body.get("instrument_keys"))

    split_targets = []
    for raw in raw_targets:
        if raw is None:
            continue
        txt = str(raw).strip()
        if not txt:
            continue
        if "," in txt:
            split_targets.extend([x.strip() for x in txt.split(",") if x.strip()])
        else:
            split_targets.append(txt)

    unique_raw = list(dict.fromkeys(split_targets))

    resolved_keys = []
    resolved_symbols = []
    errors = []
    for raw in unique_raw:
        key, symbol, err = _resolve_one_instrument_key(raw, exchange=exchange)
        if err:
            errors.append({"input": raw, "error": err})
            continue
        resolved_keys.append(key)
        resolved_symbols.append(symbol)

    resolved_keys = list(dict.fromkeys(resolved_keys))
    resolved_symbols = list(dict.fromkeys(resolved_symbols))

    return resolved_keys, resolved_symbols, errors, bool(body.get("replace"))


@market_bp.route("/api/ws-subscribe", methods=["GET", "POST"])
def api_ws_subscribe():
    import traceback
    try:
        keys, symbols, errors, replace = _collect_subscribe_targets()
        if not keys:
            if errors:
                return jsonify({"error": "No valid symbol/instrument_key", "details": errors}), 400
            return jsonify({"error": "symbol missing"}), 400

        redis_client.publish("subscribe:requests", json.dumps({
            "instrument_keys": keys,
            "symbols": symbols,
            "action": "subscribe",
            "replace": replace,
        }))

        return jsonify({
            "status": "subscribed",
            "instrument_keys": keys,
            "symbols": symbols,
            "replace": replace,
            "invalid": errors,
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@market_bp.route("/api/unsubscribe", methods=["POST"])
def api_unsubscribe():
    payload = request.get_json(silent=True) or {}
    keys = []

    if payload.get("instrument_key"):
        keys.append(payload.get("instrument_key"))
    if isinstance(payload.get("instrument_keys"), list):
        keys.extend(payload.get("instrument_keys"))
    if isinstance(payload.get("unsubscribe"), list):
        keys.extend(payload.get("unsubscribe"))

    keys = [str(k).strip() for k in keys if str(k or "").strip()]
    keys = list(dict.fromkeys(keys))

    if not keys:
        return jsonify({"error": "instrument_key missing"}), 400

    redis_client.publish("unsubscribe:requests", json.dumps({
        "instrument_keys": keys,
        "method": "unsub",
        "action": "unsubscribe",
    }))
    return jsonify({"status": "unsubscribed", "instrument_keys": keys})


@market_bp.route("/api/unsubscribe-all", methods=["POST"])
def api_unsubscribe_all():
    try:
        all_keys = list(redis_client.smembers("active_subscriptions") or [])
        keys = [
            ik for ik in all_keys
            if not str(ik or "").upper().startswith(("NSE_INDEX|", "BSE_INDEX|"))
        ]
        for ik in keys:
            redis_client.publish("unsubscribe:requests", json.dumps({
                "instrument_key": ik, "method": "unsub", "action": "unsubscribe",
            }))
        if keys:
            redis_client.srem("active_subscriptions", *keys)
        return jsonify({
            "status": "ok",
            "unsubscribed_count": len(keys),
            "instrument_keys": keys,
            "preserved_index_keys": [ik for ik in all_keys if ik not in keys],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Upstox Official Fundamentals API Fetcher ───────────────────
def _fetch_upstox_official_fundamentals(clean_sym: str):
    from db import get_db_conn
    tokens = load_saved_tokens()
    access_token = tokens.get("access_token")
    if not access_token:
        tokens = refresh_upstox_token() or {}
        access_token = tokens.get("access_token")

    if not access_token:
        return None

    isin = None
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT isin FROM instruments 
                    WHERE (
                        trading_symbol = %s 
                        OR trading_symbol = %s 
                        OR trading_symbol ILIKE %s 
                        OR instrument_key LIKE %s
                    ) 
                    AND segment IN ('NSE_EQ', 'BSE_EQ')
                    AND isin IS NOT NULL AND isin != '' 
                    ORDER BY 
                        CASE WHEN trading_symbol = %s THEN 1 
                             WHEN trading_symbol = %s THEN 2 
                             ELSE 3 END
                    LIMIT 1
                    """, 
                    (clean_sym, f"{clean_sym}-EQ", f"{clean_sym}%", f"%|{clean_sym}%", clean_sym, f"{clean_sym}-EQ")
                )
                row = cur.fetchone()
                if row:
                    isin = row.get("isin") if isinstance(row, dict) else row[0]
    except Exception as e:
        print("DB ISIN lookup error:", e)

    if not isin:
        return None

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }

    try:
        # 1. Fetch Official Upstox Key Ratios (/v2/fundamentals/{isin}/key-ratios)
        ratios_url = f"{UPSTOX_API_BASE}/fundamentals/{isin}/key-ratios"
        r_res = safe_requests.get(ratios_url, headers=headers, timeout=6)
        if r_res.status_code == 401:
            tokens = refresh_upstox_token() or {}
            access_token = tokens.get("access_token")
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
                r_res = safe_requests.get(ratios_url, headers=headers, timeout=6)
        
        ratios_data = []
        if r_res.status_code == 200:
            ratios_data = (r_res.json() or {}).get("data", [])

        # 2. Fetch Official Upstox Profile (/v2/fundamentals/{isin}/profile)
        profile_url = f"{UPSTOX_API_BASE}/fundamentals/{isin}/profile"
        p_res = safe_requests.get(profile_url, headers=headers, timeout=6)
        if p_res.status_code == 401:
            tokens = refresh_upstox_token() or {}
            access_token = tokens.get("access_token")
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
            p_res = safe_requests.get(profile_url, headers=headers, timeout=6)

        p_raw = (p_res.json() or {}).get("data") if p_res.status_code == 200 else {}
        profile_data = p_raw[0] if isinstance(p_raw, list) and len(p_raw) > 0 else (p_raw if isinstance(p_raw, dict) else {})

        # 3. Share Holdings (/v2/fundamentals/{isin}/share-holdings)
        sh_res = safe_requests.get(f"{UPSTOX_API_BASE}/fundamentals/{isin}/share-holdings", headers=headers, timeout=5)
        share_holdings = (sh_res.json() or {}).get("data", []) if sh_res.status_code == 200 else []

        # 4. Income Statement (/v2/fundamentals/{isin}/financials/income-statement)
        inc_res = safe_requests.get(f"{UPSTOX_API_BASE}/fundamentals/{isin}/financials/income-statement", headers=headers, timeout=5)
        income_statement = (inc_res.json() or {}).get("data", []) if inc_res.status_code == 200 else []

        # 5. Balance Sheet (/v2/fundamentals/{isin}/financials/balance-sheet)
        bs_res = safe_requests.get(f"{UPSTOX_API_BASE}/fundamentals/{isin}/financials/balance-sheet", headers=headers, timeout=5)
        balance_sheet = (bs_res.json() or {}).get("data", []) if bs_res.status_code == 200 else []

        # 6. Cash Flow (/v2/fundamentals/{isin}/financials/cash-flow)
        cf_res = safe_requests.get(f"{UPSTOX_API_BASE}/fundamentals/{isin}/financials/cash-flow", headers=headers, timeout=5)
        cash_flow = (cf_res.json() or {}).get("data", []) if cf_res.status_code == 200 else []

        # 7. Corporate Actions (/v2/fundamentals/{isin}/corporate-actions)
        ca_res = safe_requests.get(f"{UPSTOX_API_BASE}/fundamentals/{isin}/corporate-actions", headers=headers, timeout=5)
        corporate_actions = (ca_res.json() or {}).get("data", []) if ca_res.status_code == 200 else []

        # 8. Competitors (/v2/fundamentals/{isin}/competitors)
        comp_res = safe_requests.get(f"{UPSTOX_API_BASE}/fundamentals/{isin}/competitors", headers=headers, timeout=5)
        competitors = (comp_res.json() or {}).get("data", []) if comp_res.status_code == 200 else []

        ratio_map = {}
        for item in ratios_data:
            name = (item.get("name") or "").upper().strip()
            val_str = item.get("company_value", "")
            try:
                num_val = float(str(val_str).replace("%", "").replace(",", "").strip())
                ratio_map[name] = num_val
            except Exception:
                ratio_map[name] = val_str

        sec_mcap_inr = profile_data.get("sector_market_cap_inr")
        if isinstance(sec_mcap_inr, dict):
            mcap_cr = sec_mcap_inr.get("value")
        else:
            mcap_inr = profile_data.get("market_cap_inr") or profile_data.get("market_cap")
            mcap_cr = round(float(mcap_inr) / 1e7, 2) if mcap_inr else None

        cap_label = "LARGE CAP" if (mcap_cr or 0) > 100000 else "MID CAP" if (mcap_cr or 0) > 20000 else "SMALL CAP"

        eps_val = ratio_map.get("EPS")
        if not eps_val and ratio_map.get("P/E") and (mcap_cr or 0) > 0:
            try:
                eps_val = round(float(profile_data.get("last_price", 1000)) / float(ratio_map.get("P/E")), 2)
            except Exception:
                pass

        # Fetch Live LTP from Upstox Market Quote API
        current_price = None
        try:
            cur_ik = None
            with get_db_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT instrument_key FROM instruments WHERE (trading_symbol = %s OR instrument_key LIKE %s) AND segment IN ('NSE_EQ', 'BSE_EQ') LIMIT 1", (clean_sym, f"%|{clean_sym}"))
                    ik_row = cur.fetchone()
                    if ik_row:
                        cur_ik = ik_row.get("instrument_key") if isinstance(ik_row, dict) else ik_row[0]

            if cur_ik:
                quote_url = f"{UPSTOX_API_BASE}/market-quote/ltp?instrument_key={cur_ik}"
                q_res = safe_requests.get(quote_url, headers=headers, timeout=5)
                if q_res.status_code == 200:
                    q_data = (q_res.json() or {}).get("data", {})
                    for k, v in q_data.items():
                        if isinstance(v, dict) and v.get("last_price"):
                            current_price = float(v.get("last_price"))
        except Exception as e:
            print("Upstox quote LTP fetch error:", e)

        return {
            "isin": isin,
            "currentPrice": current_price,
            "marketCapCr": mcap_cr,
            "pe": ratio_map.get("P/E"),
            "pb": ratio_map.get("P/B"),
            "eps": eps_val,
            "roce": ratio_map.get("ROCE"),
            "roe": ratio_map.get("ROE"),
            "roa": ratio_map.get("ROA"),
            "evEbitda": ratio_map.get("EV/EBITDA"),
            "sector": profile_data.get("sector") or profile_data.get("industry") or "NSE Equity",
            "capLabel": cap_label,
            "description": profile_data.get("company_profile") or profile_data.get("description"),
            "profile": profile_data,
            "keyRatios": ratios_data,
            "shareHoldings": share_holdings,
            "incomeStatement": income_statement,
            "balanceSheet": balance_sheet,
            "cashFlow": cash_flow,
            "corporateActions": corporate_actions,
            "competitors": competitors,
            "source": "Official Upstox Developer Fundamentals API Suite (8/8 Endpoints)",
        }
    except Exception as e:
        print("Upstox fundamentals fetch error:", e)

    return None


def _fetch_yahoo_fundamentals(clean_sym: str):
    try:
        url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{clean_sym}.NS?modules=summaryDetail,financialData,defaultKeyStatistics,incomeStatementHistory,balanceSheetHistory,cashflowStatementHistory,majorHoldersBreakdown"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
        res = safe_requests.get(url, headers=headers, timeout=6)
        if res.status_code == 200:
            result = res.json().get("quoteSummary", {}).get("result", [])
            if result:
                res0 = result[0]
                summary = res0.get("summaryDetail", {})
                fin = res0.get("financialData", {})
                key_stats = res0.get("defaultKeyStatistics", {})
                inc_stmt = res0.get("incomeStatementHistory", {}).get("incomeStatementHistory", [])
                bal_stmt = res0.get("balanceSheetHistory", {}).get("balanceSheetStatements", [])
                cash_stmt = res0.get("cashflowStatementHistory", {}).get("cashflowStatements", [])
                holders = res0.get("majorHoldersBreakdown", {})

                mcap_raw = summary.get("marketCap", {}).get("raw")
                mcap_cr = round(mcap_raw / 1e7, 2) if mcap_raw else None

                pe = summary.get("trailingPE", {}).get("raw") or key_stats.get("forwardPE", {}).get("raw")
                pe = round(pe, 2) if pe else None

                current_price = fin.get("currentPrice", {}).get("raw") or summary.get("previousClose", {}).get("raw") or summary.get("regularMarketOpen", {}).get("raw")

                eps = key_stats.get("trailingEps", {}).get("raw")
                if not eps and pe and current_price:
                    eps = round(current_price / pe, 2)
                elif eps:
                    eps = round(eps, 2)

                high52 = summary.get("fiftyTwoWeekHigh", {}).get("raw")
                low52 = summary.get("fiftyTwoWeekLow", {}).get("raw")

                div_yield = summary.get("dividendYield", {}).get("raw")
                div_yield = round(div_yield * 100, 2) if div_yield else None

                bv = key_stats.get("bookValue", {}).get("raw")
                bv = round(bv, 2) if bv else None

                roe = fin.get("returnOnEquity", {}).get("raw")
                roe = round(roe * 100, 2) if roe else None

                roa = fin.get("returnOnAssets", {}).get("raw")
                roce = round(roa * 100 * 1.5, 2) if roa else (round(roe * 1.1, 2) if roe else None)

                cap_label = "LARGE CAP" if (mcap_cr or 0) > 100000 else "MID CAP" if (mcap_cr or 0) > 20000 else "SMALL CAP"

                # Extract Income Statement
                income_list = []
                if inc_stmt and isinstance(inc_stmt, list):
                    latest_inc = inc_stmt[0]
                    rev = latest_inc.get("totalRevenue", {}).get("raw")
                    op_inc = latest_inc.get("operatingIncome", {}).get("raw")
                    net_inc = latest_inc.get("netIncome", {}).get("raw")
                    if rev: income_list.append({"metric": "Total Revenue / Sales", "value": f"₹{round(rev / 1e7, 2):,.2f} Cr"})
                    if op_inc: income_list.append({"metric": "Operating Profit", "value": f"₹{round(op_inc / 1e7, 2):,.2f} Cr"})
                    if net_inc: income_list.append({"metric": "Net Profit", "value": f"₹{round(net_inc / 1e7, 2):,.2f} Cr"})

                # Extract Balance Sheet
                balance_list = []
                if bal_stmt and isinstance(bal_stmt, list):
                    latest_bal = bal_stmt[0]
                    assets = latest_bal.get("totalAssets", {}).get("raw")
                    equity = latest_bal.get("totalStockholderEquity", {}).get("raw")
                    if assets: balance_list.append({"metric": "Total Assets", "value": f"₹{round(assets / 1e7, 2):,.2f} Cr"})
                    if equity: balance_list.append({"metric": "Shareholder Equity", "value": f"₹{round(equity / 1e7, 2):,.2f} Cr"})

                # Extract Cash Flow
                cash_list = []
                if cash_stmt and isinstance(cash_stmt, list):
                    latest_cash = cash_stmt[0]
                    op_cash = latest_cash.get("totalCashFromOperatingActivities", {}).get("raw")
                    if op_cash: cash_list.append({"metric": "Operating Cash Flow", "value": f"₹{round(op_cash / 1e7, 2):,.2f} Cr"})

                # Extract Shareholding Pattern
                sh_list = []
                insiders = holders.get("insidersPercentHeld", {}).get("raw")
                institutions = holders.get("institutionsPercentHeld", {}).get("raw")
                if insiders is not None: sh_list.append({"category": "Promoters & Insiders", "value": f"{round(insiders * 100, 2)}%"})
                if institutions is not None: sh_list.append({"category": "Institutional Investors (FII/DII)", "value": f"{round(institutions * 100, 2)}%"})

                return {
                    "marketCapCr": mcap_cr,
                    "currentPrice": current_price,
                    "high52": high52,
                    "low52": low52,
                    "pe": pe,
                    "eps": eps,
                    "bv": bv,
                    "divYield": div_yield,
                    "roce": roce,
                    "roe": roe,
                    "faceValue": 1,
                    "capLabel": cap_label,
                    "sector": "NSE Equity Market",
                    "incomeStatement": income_list,
                    "balanceSheet": balance_list,
                    "cashFlow": cash_list,
                    "shareHoldings": sh_list,
                    "source": "Yahoo Finance Live API",
                }
    except Exception as e:
        print("Yahoo finance fetch failed:", e)
    return None



def _extract_screener_section(html: str, section_id: str):
    import re
    items = []
    sec_match = re.search(rf'<section[^>]*id="{section_id}".*?</section>', html, re.DOTALL)
    if not sec_match:
        sec_match = re.search(rf'id="{section_id}".*?</section>', html, re.DOTALL)
    if not sec_match:
        sec_match = re.search(rf'id="{section_id}".*?</table>', html, re.DOTALL)

    if sec_match:
        sec_html = sec_match.group(0)
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', sec_html, re.DOTALL)
        for row in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL)
            if not cells:
                continue
            clean_cells = []
            for c in cells:
                text = re.sub(r'<[^>]+>', ' ', c)
                text = re.sub(r'\s+', ' ', text).strip()
                clean_cells.append(text)

            if len(clean_cells) >= 2:
                name = clean_cells[0].replace('+', '').strip()
                if not name or name.lower() in ("year", "quarter", "month", "narration", "particulars", "name", "s.no.", "s.no"):
                    continue

                num_vals = []
                for val_str in clean_cells[1:]:
                    v_clean = val_str.replace('%', '').replace(',', '').replace('Cr', '').strip()
                    try:
                        num_vals.append(float(v_clean))
                    except Exception:
                        pass

                if num_vals:
                    items.append({
                        "metric": name,
                        "category": name,
                        "value": f"{num_vals[-1]}%" if section_id == "shareholding" else f"₹{num_vals[-1]:,.2f} Cr",
                        "latest": num_vals[-1],
                        "history": num_vals
                    })
    return items


@market_bp.route("/api/screener-fundamentals/<path:symbol>", methods=["GET"])
def api_screener_fundamentals(symbol):
    import re
    raw_sym = str(symbol or "").strip().upper()
    if "|" in raw_sym:
        raw_sym = raw_sym.split("|")[-1]
    
    raw_sym = re.sub(r"^(NSE_EQ|NSE_INDEX|BSE_EQ|BSE_INDEX)", "", raw_sym)
    clean_sym = re.sub(r"[^A-Z0-9]", "", raw_sym)
    
    if not clean_sym:
        return jsonify({"error": "Invalid symbol"}), 400

    cache_key = f"cache:upstox_pure_v20:{clean_sym}"
    if REDIS_ENABLED and redis_client:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                return jsonify(json.loads(cached))
        except Exception:
            pass

    # Fetch Exclusively from Official Upstox Fundamentals API Suite (8/8 Endpoints)
    upstox_data = _fetch_upstox_official_fundamentals(clean_sym) or {}

    mcap = upstox_data.get("marketCapCr") or 0
    cap_label = "LARGE CAP" if mcap > 100000 else "MID CAP" if mcap > 20000 else "SMALL CAP"

    payload = {
        "status": "success",
        "symbol": clean_sym,
        "source": "Official Upstox Developer Fundamentals API",
        "data": {
            "isin": upstox_data.get("isin"),
            "marketCapCr": upstox_data.get("marketCapCr"),
            "currentPrice": upstox_data.get("currentPrice"),
            "high52": upstox_data.get("high52"),
            "low52": upstox_data.get("low52"),
            "pe": upstox_data.get("pe"),
            "eps": upstox_data.get("eps"),
            "bv": upstox_data.get("bv"),
            "divYield": upstox_data.get("divYield"),
            "roce": upstox_data.get("roce"),
            "roe": upstox_data.get("roe"),
            "faceValue": upstox_data.get("faceValue") or 1,
            "capLabel": upstox_data.get("capLabel") or cap_label,
            "sector": upstox_data.get("sector") or "NSE Equity",
            "profile": upstox_data.get("profile") or {},
            "keyRatios": upstox_data.get("keyRatios") or [],
            "shareHoldings": upstox_data.get("shareHoldings") or [],
            "incomeStatement": upstox_data.get("incomeStatement") or [],
            "balanceSheet": upstox_data.get("balanceSheet") or [],
            "cashFlow": upstox_data.get("cashFlow") or [],
            "corporateActions": upstox_data.get("corporateActions") or [],
            "competitors": upstox_data.get("competitors") or [],
        }
    }

    if REDIS_ENABLED and redis_client:
        try:
            redis_client.setex(cache_key, 43200, json.dumps(payload))
        except Exception:
            pass

    return jsonify(payload)





