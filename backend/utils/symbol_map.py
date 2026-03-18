# utils/symbol_map.py
import gzip, json, os

SYMBOL_TO_KEY: dict = {}

def load_symbol_map():
    global SYMBOL_TO_KEY

    # Import here to avoid circular import (config imports nothing from utils)
    from config import BASE_DIR

    inst_path = os.path.join(BASE_DIR, "upstox_instruments.json.gz")
    if not os.path.exists(inst_path):
        print("❌ Instruments file missing — SYMBOL_TO_KEY empty")
        return

    try:
        with gzip.open(inst_path, "rt", encoding="utf-8") as f:
            instruments = json.load(f)

        print(f"📦 Total instruments in file: {len(instruments)}")

        temp    = {}
        skipped = 0

        for i in instruments:
            symbol = (
                i.get("symbol") or i.get("trading_symbol") or i.get("tradingsymbol") or ""
            ).upper().strip()
            if not symbol:
                continue

            raw_key  = (i.get("instrument_key") or i.get("instrumentKey") or i.get("token") or "").strip()
            isin     = (i.get("isin") or "").upper().strip()
            exchange = (i.get("exchange") or i.get("segment") or "").upper()

            if "NSE" in exchange:
                exchange = "NSE"
            elif "BSE" in exchange:
                exchange = "BSE"
            else:
                # Keep INDEX instruments
                if i.get("instrument_type", "").upper() == "INDEX" and raw_key:
                    temp.setdefault(symbol, {})["INDEX"] = raw_key
                continue

            temp.setdefault(symbol, {})

            if isin:
                # Best case — standard Upstox ISIN key
                temp[symbol][exchange] = f"{exchange}_EQ|{isin}"

            elif raw_key and "|" in raw_key:
                # Raw key already in correct Upstox format
                temp[symbol][exchange] = raw_key

            elif raw_key:
                # ✅ FIX: raw token exists but no pipe — construct the key
                temp[symbol][exchange] = f"{exchange}_EQ|{raw_key}"

            else:
                # Truly nothing usable
                skipped += 1
                continue

        SYMBOL_TO_KEY = temp
        print(f"🎯 SYMBOL_TO_KEY: {len(SYMBOL_TO_KEY)} symbols loaded, {skipped} skipped (no key)")

    except Exception as e:
        print("❌ SYMBOL_TO_KEY build failed:", e)
        SYMBOL_TO_KEY = {}
