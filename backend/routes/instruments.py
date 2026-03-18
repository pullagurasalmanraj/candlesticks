# routes/instruments.py
# ================================================================
#  Instruments blueprint:
#    GET  /api/instruments        — search
#    POST /api/admin/sync-instruments
#    GET  /api/logo/<symbol>
#    POST /api/logo/seed
# ================================================================
import gzip, json, os, traceback
from datetime import datetime, timezone

import psycopg2.extras
from flask import Blueprint, request, jsonify, redirect
from psycopg2.extras import execute_values

from config  import BASE_DIR
from db      import get_db_conn

instruments_bp = Blueprint("instruments", __name__)


def classify(segment, instrument_type):
    seg   = (segment or "").upper()
    itype = (instrument_type or "").upper()
    if seg in ("NSE_EQ", "BSE_EQ"):                          return "EQUITY",    True
    if seg == "NSE_FO" and itype in ("FUTIDX", "FUTSTK"):    return "FUTURE",    True
    if seg == "NSE_FO" and itype in ("CE","PE","OPTIDX","OPTSTK"): return "OPTION", True
    if seg.startswith("MCX"):                                 return "COMMODITY", False
    if "BOND" in itype:                                       return "BOND",      False
    if itype == "INDEX":                                      return "INDEX",     False
    return "OTHER", False


def ms_to_date(ms):
    if not ms: return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date()
    except Exception:
        return None


def sync_instruments_core():
    inst_path = os.path.join(BASE_DIR, "upstox_instruments.json.gz")
    if not os.path.exists(inst_path):
        raise FileNotFoundError("Instruments file missing")

    with gzip.open(inst_path, "rt", encoding="utf-8") as f:
        instruments = json.load(f)

    snapshot_ts = datetime.utcnow()
    rows, skipped = [], 0

    for i in instruments:
        ik = i.get("instrument_key")
        if not ik:
            skipped += 1
            continue
        asset_class, is_tradeable = classify(i.get("segment"), i.get("instrument_type"))
        seg = (i.get("segment") or "").upper()
        exchange = "NSE" if seg.startswith("NSE") else "BSE" if seg.startswith("BSE") else "MCX"
        rows.append((
            ik, (i.get("trading_symbol") or "").upper(), i.get("name"), exchange,
            i.get("segment"), i.get("instrument_type"), i.get("isin"),
            i.get("underlying_symbol"), i.get("strike_price"), ms_to_date(i.get("expiry")),
            i.get("lot_size"), i.get("minimum_lot"), i.get("qty_multiplier"),
            i.get("exchange_token"), i.get("tick_size"), asset_class, is_tradeable,
            snapshot_ts, True,
        ))

    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE instruments SET is_active = FALSE")
            execute_values(cur, """
                INSERT INTO instruments (
                    instrument_key,trading_symbol,name,exchange,segment,instrument_type,
                    isin,underlying,strike_price,expiry,lot_size,minimum_lot,qty_multiplier,
                    exchange_token,tick_size,asset_class,is_tradeable,last_seen_at,is_active
                ) VALUES %s
                ON CONFLICT (instrument_key) DO UPDATE SET
                    trading_symbol=EXCLUDED.trading_symbol,name=EXCLUDED.name,
                    exchange=EXCLUDED.exchange,segment=EXCLUDED.segment,
                    instrument_type=EXCLUDED.instrument_type,isin=EXCLUDED.isin,
                    underlying=EXCLUDED.underlying,strike_price=EXCLUDED.strike_price,
                    expiry=EXCLUDED.expiry,lot_size=EXCLUDED.lot_size,
                    minimum_lot=EXCLUDED.minimum_lot,qty_multiplier=EXCLUDED.qty_multiplier,
                    exchange_token=EXCLUDED.exchange_token,tick_size=EXCLUDED.tick_size,
                    asset_class=EXCLUDED.asset_class,is_tradeable=EXCLUDED.is_tradeable,
                    last_seen_at=EXCLUDED.last_seen_at,is_active=TRUE
            """, rows, page_size=1000)
    print(f"✅ Sync complete: {len(rows)} rows, {skipped} skipped")


@instruments_bp.route("/api/admin/sync-instruments", methods=["POST"])
def sync_instruments():
    try:
        sync_instruments_core()
        return jsonify({"status": "SUCCESS"})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@instruments_bp.route("/api/instruments", methods=["GET"])
def api_instruments():
    q = request.args.get("q", "").strip().upper()
    if len(q) < 2:
        return jsonify({"instruments": []})

    sql = """
        SELECT trading_symbol AS symbol, name, exchange, segment, instrument_type,
               isin, underlying, strike_price, expiry, lot_size, minimum_lot,
               qty_multiplier, instrument_key, exchange_token, tick_size
        FROM v_search_universe
        WHERE is_tradeable = true
          AND (trading_symbol ILIKE %s OR name ILIKE %s)
        ORDER BY
            CASE
                WHEN trading_symbol = %s          THEN 0
                WHEN trading_symbol ILIKE %s       THEN 1
                WHEN segment IN ('NSE_EQ','BSE_EQ') THEN 2
                WHEN segment = 'NSE_INDEX'          THEN 3
                WHEN segment = 'NSE_FO' AND instrument_type IN ('FUTIDX','FUTSTK') THEN 4
                WHEN segment = 'NSE_FO' AND instrument_type IN ('CE','PE') THEN 5
                ELSE 6
            END, LENGTH(trading_symbol), trading_symbol
        LIMIT 50
    """
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, [f"{q}%", f"{q}%", q, f"{q}%"])
            rows = cur.fetchall()
    return jsonify({"instruments": rows})
