# wsserver.py
"""
Upstox -> Redis -> Local WebSocket bridge (Market Feed V3)

FIXES:
  1. decode_responses=True  — everything in Redis is stored/read as str.
  2. No .encode() calls     — decode_responses=True handles encoding automatically.
  3. mode="full"            — only "full" includes marketOHLC with I1 interval data.
  4. Startup re-subscribe   — replays active_subscriptions SET on every (re)connect.
  5. Proper task structure  — consumer, sender, keepalive as independent asyncio tasks.
  6. uri always refreshed   — WSS URL contains a one-time code= that expires on use.
                              Always extract fresh uri from every authorize response.
  7. Redis-only token       — os.getenv("UPSTOX_ACCESS_TOKEN") is NEVER used for the
                              authorize call. The env var may hold a stale token from
                              container start time. Redis always has the freshest token
                              written by backend after OAuth. Using the env var caused
                              permanent 401 after token refresh because the old token
                              was truthy and short-circuited the Redis lookup.
"""

import os
import json
import time
import ssl
import base64
import asyncio
import traceback
import threading
from typing import Set

import requests
import redis
import websockets

# ── Optional protobuf ─────────────────────────────────────────────
try:
    import MarketDataFeedV3_pb2 as pb
    from google.protobuf.json_format import MessageToDict
    print("✅ Protobuf loaded")
except Exception:
    pb = None
    MessageToDict = None
    print("⚠️  Protobuf not available — falling back to raw decode")

# ── Optional upstox_client SDK (not required) ─────────────────────
try:
    from upstox_client import MarketDataStreamerV3, Configuration, ApiClient  # type: ignore
except Exception:
    MarketDataStreamerV3 = None
    Configuration = None
    ApiClient = None

# ── Config ────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://:linux123@127.0.0.1:6379/10")
WS_HOST = os.getenv("WS_HOST", "0.0.0.0")
WS_PORT = int(os.getenv("WS_PORT", "9000"))
SKIP_SSL_VERIFY = os.getenv("SKIP_SSL_VERIFY", "0") in ("1", "true", "True")
REDIS_SUBSCRIBE_CHANNEL = "subscribe:requests"
REDIS_TICKS_CHANNEL = "ticks:live"
REDIS_UNSUB_CHANNEL = "unsubscribe:requests"
REDIS_ACTIVE_SUBS_KEY = "active_subscriptions"
REDIS_READY_RETRY_SECONDS = float(os.getenv("REDIS_READY_RETRY_SECONDS", "2"))
REDIS_OP_RETRIES = max(1, int(os.getenv("REDIS_OP_RETRIES", "2")))
REDIS_OP_RETRY_DELAY = float(os.getenv("REDIS_OP_RETRY_DELAY", "0.25"))

# ── Globals ───────────────────────────────────────────────────────
redis_client = redis.Redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
    health_check_interval=30,
    retry_on_timeout=True,
    socket_keepalive=True,
)
CONNECTED_CLIENTS: Set = set()
CURRENT_SUBS = set()
SUBSCRIBE_QUEUE = asyncio.Queue()
ASYNC_LOOP: asyncio.AbstractEventLoop | None = None

# Canonicalize known index aliases to valid Upstox instrument keys.
INDEX_KEY_ALIASES = {
    "NSE_INDEX|NIFTY_50": "NSE_INDEX|Nifty 50",
    "NSE_INDEX|NIFTY 50": "NSE_INDEX|Nifty 50",
    "NSE_INDEX|NIFTY": "NSE_INDEX|Nifty 50",
    "NSE_INDEX|BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "NSE_INDEX|NIFTY BANK": "NSE_INDEX|Nifty Bank",
    "NSE_INDEX|NIFTY_NEXT_50": "NSE_INDEX|Nifty Next 50",
    "NSE_INDEX|NIFTY NEXT 50": "NSE_INDEX|Nifty Next 50",
    "NSE_INDEX|NIFTYNXT50": "NSE_INDEX|Nifty Next 50",
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "NIFTYNXT50": "NSE_INDEX|Nifty Next 50",
    "NEXT50": "NSE_INDEX|Nifty Next 50",
    "SENSEX": "BSE_INDEX|SENSEX",
}


def canonicalize_instrument_key(key: str) -> str:
    raw = str(key or "").strip()
    if not raw:
        return ""
    return INDEX_KEY_ALIASES.get(raw.upper(), raw)


def canonicalize_instrument_keys(keys) -> list[str]:
    out = []
    seen = set()
    for key in keys or []:
        norm = canonicalize_instrument_key(key)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def is_index_instrument_key(instrument_key: str) -> bool:
    k = str(instrument_key or "").upper()
    return k.startswith("NSE_INDEX|") or k.startswith("BSE_INDEX|")


def daily_tick_storage_key(instrument_key: str, day_iso: str) -> str:
    bucket = "index" if is_index_instrument_key(instrument_key) else "instrument"
    return f"ticks:{bucket}:{day_iso}:{instrument_key}"


def log(*args, **kwargs):
    print(*args, **kwargs, flush=True)


def wait_for_redis_ready():
    attempts = 0
    while True:
        attempts += 1
        try:
            redis_client.ping()
            log("Redis connection ready")
            return
        except redis.exceptions.RedisError as exc:
            if attempts == 1 or attempts % 5 == 0:
                log(
                    f"Redis not ready yet: {exc}. "
                    f"Retrying in {REDIS_READY_RETRY_SECONDS}s ..."
                )
            time.sleep(REDIS_READY_RETRY_SECONDS)


def redis_call(method, *args, default=None, **kwargs):
    for attempt in range(1, REDIS_OP_RETRIES + 1):
        try:
            fn = getattr(redis_client, method)
            return fn(*args, **kwargs)
        except redis.exceptions.RedisError as exc:
            if attempt >= REDIS_OP_RETRIES:
                log(f"Redis {method} failed after {attempt} attempt(s): {exc}")
                return default
            time.sleep(REDIS_OP_RETRY_DELAY * attempt)


# ── Token ─────────────────────────────────────────────────────────
def get_access_token_from_redis() -> str:
    """
    Always read token from Redis.
    Never use os.getenv("UPSTOX_ACCESS_TOKEN") for authorize calls — the env var
    is frozen at container start and may hold a stale/expired token even after
    the backend has refreshed it via OAuth. Redis always has the latest token.
    """
    try:
        raw = redis_call("get", "upstox:tokens", default="")
        if not raw:
            return ""
        data = json.loads(raw)
        return data.get("access_token", "")
    except Exception:
        return ""


# ── Protobuf decode ───────────────────────────────────────────────
def try_decode_tick(raw_bytes: bytes) -> str:
    if pb is not None:
        try:
            feed = pb.FeedResponse()
            feed.ParseFromString(raw_bytes)
            if MessageToDict is not None:
                try:
                    d = MessageToDict(feed, preserving_proto_field_name=True)
                    return json.dumps({"proto_parsed": True, "data": d})
                except Exception:
                    return json.dumps({
                        "proto_parsed": True,
                        "raw_base64": base64.b64encode(raw_bytes).decode(),
                    })
        except Exception:
            pass
    try:
        txt = raw_bytes.decode("utf-8")
        try:
            return json.dumps({"proto_parsed": False, "data": json.loads(txt)})
        except Exception:
            return json.dumps({"proto_parsed": False, "raw_text": txt})
    except Exception:
        return json.dumps({"proto_parsed": False, "raw_base64": base64.b64encode(raw_bytes).decode()})


# ── Broadcast to local WS clients ────────────────────────────────
async def broadcast_to_clients(payload_str: str):
    dead = []
    for ws in list(CONNECTED_CLIENTS):
        try:
            await ws.send(payload_str)
        except Exception:
            dead.append(ws)
    for ws in dead:
        CONNECTED_CLIENTS.discard(ws)


# ── Subscribe payload ─────────────────────────────────────────────
def build_subscribe_payload(instrument_keys, mode="full", guid=None):
    if guid is None:
        guid = str(int(time.time() * 1000))
    return {
        "guid": guid,
        "method": "sub",
        "data": {"mode": mode, "instrumentKeys": instrument_keys},
    }


# ── WSS URL extractor ─────────────────────────────────────────────
def find_wss(obj):
    if isinstance(obj, str) and obj.startswith("wss://"):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            r = find_wss(v)
            if r:
                return r
    if isinstance(obj, list):
        for v in obj:
            r = find_wss(v)
            if r:
                return r


# ── Upstox WSS worker ─────────────────────────────────────────────
async def upstox_wss_worker(loop, subscription_queue: asyncio.Queue):

    # FIX 7: always read from Redis, never from env var
    token = get_access_token_from_redis()

    if not token:
        log("🔴 No token in Redis — waiting for backend OAuth...")
        while True:
            await asyncio.sleep(10)
            token = get_access_token_from_redis()
            if token:
                log("🟢 Token found in Redis, connecting...")
                break

    def authorize_call(t):
        r = requests.get(
            "https://api.upstox.com/v3/feed/market-data-feed/authorize",
            headers={"Accept": "application/json", "Authorization": f"Bearer {t}"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    while True:
        try:
            # FIX 7: always read fresh token from Redis on every loop iteration.
            # Never use os.getenv — env var is frozen at container start time and
            # will be stale after the backend refreshes the token via OAuth.
            token = get_access_token_from_redis()

            if not token:
                log("🔴 No token in Redis")
                await asyncio.sleep(5)
                continue

            log(f"🔑 Token (first 30): {token[:30]}")
            log("🔁 Authorizing Upstox feed...")
            j = await asyncio.to_thread(authorize_call, token)

            # FIX 6: always extract uri fresh — the WSS URL contains a one-time
            # code= parameter that expires immediately after use. Never cache uri.
            uri = find_wss(j)

            if not uri:
                raise RuntimeError(f"No WSS URL in authorize response: {j}")

            log("🔗 WSS URL:", uri)

            ssl_ctx = ssl.create_default_context()
            if SKIP_SSL_VERIFY:
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE

            log("🔌 Connecting to Upstox WSS...")
            async with websockets.connect(uri, ssl=ssl_ctx, max_size=None) as ws:
                log("✅ Connected to Upstox feed")

                # Re-subscribe on every (re)connect from persisted Redis SET
                saved_subs = redis_call("smembers", REDIS_ACTIVE_SUBS_KEY, default=set())
                if saved_subs:
                    normalized_subs = canonicalize_instrument_keys(saved_subs)
                    stale_subs = set(saved_subs) - set(normalized_subs)
                    for old_key in stale_subs:
                        redis_call("srem", REDIS_ACTIVE_SUBS_KEY, old_key, default=0)
                    for new_key in normalized_subs:
                        redis_call("sadd", REDIS_ACTIVE_SUBS_KEY, new_key, default=0)

                    CURRENT_SUBS.update(normalized_subs)
                    await subscription_queue.put({
                        "instrumentKeys": normalized_subs,
                        "method": "sub",
                        "mode": "full",
                    })
                    log(f"🔄 Re-subscribing {len(normalized_subs)} saved instrument(s): {normalized_subs}")

                # ── Consumer ──────────────────────────────────────
                async def consumer():
                    try:
                        async for message in ws:
                            if isinstance(message, bytes):
                                payload = try_decode_tick(message)
                            else:
                                payload = json.dumps({"proto_parsed": False, "raw_text": message})

                            redis_call("publish", REDIS_TICKS_CHANNEL, payload, default=0)

                            try:
                                tick_obj = json.loads(payload)
                                feeds = tick_obj.get("data", {}).get("feeds", {})
                                if feeds:
                                    today = time.strftime("%Y-%m-%d")
                                    for ik in feeds:
                                        key = daily_tick_storage_key(ik, today)
                                        redis_call("lpush", key, payload, default=0)
                                        redis_call("expire", key, 86400, default=False)
                            except Exception:
                                traceback.print_exc()

                            await broadcast_to_clients(payload)

                    except websockets.ConnectionClosed:
                        log("⚠️ Upstox WSS closed")
                    except Exception:
                        traceback.print_exc()
                    finally:
                        log("ℹ️ Consumer stopped")

                # ── Keepalive ─────────────────────────────────────
                async def keepalive():
                    try:
                        while True:
                            await asyncio.sleep(20)
                            try:
                                pong = await ws.ping()
                                await asyncio.wait_for(pong, timeout=10)
                            except Exception:
                                pass
                    except asyncio.CancelledError:
                        pass

                # ── Sender ────────────────────────────────────────
                async def sender():
                    try:
                        while True:
                            item = await subscription_queue.get()
                            if item is None:
                                break
                            keys = item.get("instrumentKeys") or []
                            if not keys:
                                continue
                            payload = build_subscribe_payload(
                                keys,
                                mode=item.get("mode", "full"),
                                guid=item.get("guid"),
                            )
                            if item.get("method") == "unsub":
                                payload["method"] = "unsub"
                            try:
                                await ws.send(json.dumps(payload).encode("utf-8"))
                                log(f"📨 {payload['method'].upper()} → {keys}")
                            except Exception:
                                await subscription_queue.put(item)
                                raise
                    except asyncio.CancelledError:
                        pass

                consumer_task = asyncio.create_task(consumer())
                keepalive_task = asyncio.create_task(keepalive())
                sender_task = asyncio.create_task(sender())

                try:
                    await consumer_task
                finally:
                    sender_task.cancel()
                    keepalive_task.cancel()
                    for t in (sender_task, keepalive_task):
                        try:
                            await t
                        except Exception:
                            pass

        except Exception:
            traceback.print_exc()
            log("⏳ Reconnecting in 5s...")
            await asyncio.sleep(5)


# ── Redis subscribe listener (thread) ────────────────────────────
def redis_subscribe_thread(loop, subscription_queue):
    log("Listening on subscribe:requests ...")
    while True:
        pub = None
        try:
            pub = redis_client.pubsub(ignore_subscribe_messages=True)
            pub.subscribe(REDIS_SUBSCRIBE_CHANNEL)

            for item in pub.listen():
                raw = item.get("data")
                if not raw or not isinstance(raw, str):
                    continue

                payload = json.loads(raw)
                action = (payload.get("action") or "subscribe").lower()
                ik = (
                    payload.get("instrument_key")
                    or payload.get("instrumentKey")
                    or payload.get("symbol")
                )
                ik = canonicalize_instrument_key(ik)
                if not ik:
                    continue

                log(f"Redis -> action='{action}' ik='{ik}'")

                if action in ("unsub", "unsubscribe"):
                    CURRENT_SUBS.discard(ik)
                    redis_call("srem", REDIS_ACTIVE_SUBS_KEY, ik, default=0)
                    asyncio.run_coroutine_threadsafe(
                        subscription_queue.put({"instrumentKeys": [ik], "method": "unsub"}),
                        loop,
                    )
                else:
                    if ik in CURRENT_SUBS:
                        log(f"Already subscribed: {ik}")
                        continue
                    CURRENT_SUBS.add(ik)
                    redis_call("sadd", REDIS_ACTIVE_SUBS_KEY, ik, default=0)
                    asyncio.run_coroutine_threadsafe(
                        subscription_queue.put({"instrumentKeys": [ik], "method": "sub", "mode": "full"}),
                        loop,
                    )
        except redis.exceptions.RedisError as exc:
            log(f"Redis subscribe listener disconnected: {exc}. Retrying in 2s ...")
            time.sleep(2)
        except Exception:
            traceback.print_exc()
            time.sleep(2)
        finally:
            if pub is not None:
                try:
                    pub.close()
                except Exception:
                    pass

def redis_unsubscribe_thread(loop, subscription_queue):
    log("Listening on unsubscribe:requests ...")
    while True:
        pub = None
        try:
            pub = redis_client.pubsub(ignore_subscribe_messages=True)
            pub.subscribe(REDIS_UNSUB_CHANNEL)

            for item in pub.listen():
                raw = item.get("data")
                if not raw or not isinstance(raw, str):
                    continue

                payload = json.loads(raw)
                ik = canonicalize_instrument_key(payload.get("instrument_key"))
                if not ik:
                    continue

                log(f"Redis unsub -> '{ik}'")
                CURRENT_SUBS.discard(ik)
                redis_call("srem", REDIS_ACTIVE_SUBS_KEY, ik, default=0)
                asyncio.run_coroutine_threadsafe(
                    subscription_queue.put({"instrumentKeys": [ik], "method": "unsub"}),
                    loop,
                )
        except redis.exceptions.RedisError as exc:
            log(f"Redis unsubscribe listener disconnected: {exc}. Retrying in 2s ...")
            time.sleep(2)
        except Exception:
            traceback.print_exc()
            time.sleep(2)
        finally:
            if pub is not None:
                try:
                    pub.close()
                except Exception:
                    pass

async def ws_client_handler(websocket):
    CONNECTED_CLIENTS.add(websocket)
    log(f"🟢 WS client connected ({len(CONNECTED_CLIENTS)})")
    try:
        async for msg in websocket:
            try:
                if isinstance(msg, (bytes, bytearray)):
                    msg = msg.decode("utf-8")
                parsed = json.loads(msg)
                if not isinstance(parsed, dict):
                    continue

                if "subscribe" in parsed:
                    keys = canonicalize_instrument_keys(parsed["subscribe"] or [])
                    if keys:
                        for k in keys:
                            CURRENT_SUBS.add(k)
                            redis_call("sadd", REDIS_ACTIVE_SUBS_KEY, k, default=0)
                        asyncio.create_task(
                            SUBSCRIBE_QUEUE.put({"instrumentKeys": keys, "method": "sub", "mode": "full"})
                        )
                        log("📡 WS client subscribe:", keys)

                if "unsubscribe" in parsed:
                    keys = canonicalize_instrument_keys(parsed["unsubscribe"] or [])
                    if keys:
                        for k in keys:
                            CURRENT_SUBS.discard(k)
                            redis_call("srem", REDIS_ACTIVE_SUBS_KEY, k, default=0)
                        asyncio.create_task(
                            SUBSCRIBE_QUEUE.put({"instrumentKeys": keys, "method": "unsub"})
                        )
                        log("❌ WS client unsubscribe:", keys)

                if parsed.get("action") and parsed.get("instrument_key"):
                    act = parsed["action"].lower()
                    ik = canonicalize_instrument_key(parsed["instrument_key"])
                    if not ik:
                        continue
                    if act in ("unsub", "unsubscribe"):
                        CURRENT_SUBS.discard(ik)
                        redis_call("srem", REDIS_ACTIVE_SUBS_KEY, ik, default=0)
                        asyncio.create_task(
                            SUBSCRIBE_QUEUE.put({"instrumentKeys": [ik], "method": "unsub"})
                        )
                    else:
                        CURRENT_SUBS.add(ik)
                        redis_call("sadd", REDIS_ACTIVE_SUBS_KEY, ik, default=0)
                        asyncio.create_task(
                            SUBSCRIBE_QUEUE.put({"instrumentKeys": [ik], "method": "sub", "mode": "full"})
                        )
            except Exception:
                traceback.print_exc()
    except websockets.ConnectionClosed:
        pass
    finally:
        CONNECTED_CLIENTS.discard(websocket)
        log(f"🔴 WS client disconnected ({len(CONNECTED_CLIENTS)})")


# ── Main ──────────────────────────────────────────────────────────
async def main_async():
    global ASYNC_LOOP
    ASYNC_LOOP = asyncio.get_running_loop()

    log("📡 Redis:", REDIS_URL)
    await asyncio.to_thread(wait_for_redis_ready)
    asyncio.create_task(upstox_wss_worker(ASYNC_LOOP, SUBSCRIBE_QUEUE))

    log(f"🌐 Starting local WS server ws://{WS_HOST}:{WS_PORT}")
    await websockets.serve(ws_client_handler, WS_HOST, WS_PORT, logger=None)

    for target, args in [
        (redis_subscribe_thread, (ASYNC_LOOP, SUBSCRIBE_QUEUE)),
        (redis_unsubscribe_thread, (ASYNC_LOOP, SUBSCRIBE_QUEUE)),
    ]:
        threading.Thread(target=target, args=args, daemon=True).start()

    await asyncio.Future()  # run forever


def main():
    # FIX 7: do not read UPSTOX_ACCESS_TOKEN from env into global —
    # the worker reads directly from Redis on every iteration.
    asyncio.run(main_async())


if __name__ == "__main__":
    main()


