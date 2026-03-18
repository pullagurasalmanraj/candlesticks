import requests
from datetime import datetime
from db import get_db_conn



HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nseindia.com/"
}

def vix_already_updated_today(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1
            FROM india_vix
            WHERE trade_date = CURRENT_DATE
            LIMIT 1
        """)
        return cur.fetchone() is not None


def fetch_india_vix():
    session = requests.Session()
    session.headers.update(HEADERS)

    # NSE requires homepage hit first
    session.get("https://www.nseindia.com", timeout=10)

    res = session.get(
        "https://www.nseindia.com/api/allIndices",
        timeout=10
    )
    res.raise_for_status()

    for row in res.json().get("data", []):
        if row.get("index") == "INDIA VIX":
            return {
                "trade_date": datetime.now().date(),
                "vix": float(row["last"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "previous_close": float(row["previousClose"]),
                "change_pct": float(row["percentChange"])
            }

    raise RuntimeError("INDIA VIX not found in NSE response")


def update_vix_if_needed():
    with get_db_conn() as conn:

        if vix_already_updated_today(conn):
            return  # ✅ Already done today

        vix = fetch_india_vix()

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO india_vix (
                    trade_date,
                    vix,
                    open,
                    high,
                    low,
                    previous_close,
                    change_pct
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (trade_date)
                DO UPDATE SET
                    vix = EXCLUDED.vix,
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    previous_close = EXCLUDED.previous_close,
                    change_pct = EXCLUDED.change_pct,
                    created_at = now();
            """, (
                vix["trade_date"],
                vix["vix"],
                vix["open"],
                vix["high"],
                vix["low"],
                vix["previous_close"],
                vix["change_pct"]
            ))

        conn.commit()
