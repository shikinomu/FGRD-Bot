import asyncio
import csv
import json
import signal
import sys
from datetime import datetime, timezone

import websockets

WS = "wss://api.fgrcbit.com/ws1"
SYMBOL_TOPIC = "tradeList_btcusdt"  # BTC/USDT現物の約定フィード
CSV_FILE = "prices.csv"
INTERVAL_SEC = 20

# CSVヘッダ: timestamp_iso, price, amount, raw
HEADER = ["timestamp", "price", "amount", "topic"]

stop = asyncio.Event()

def handle_sig(*_):
    stop.set()

async def ensure_header(path: str):
    try:
        with open(path, "x", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(HEADER)
    except FileExistsError:
        pass

async def log_price(row):
    with open(CSV_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(row)

async def consumer(ws):
    # 最新受信の価格を保持
    last_price = None
    last_amount = None
    last_topic = None

    async for msg in ws:
        try:
            data = json.loads(msg)
        except json.JSONDecodeError:
            continue
        sub = data.get("sub")
        payload = data.get("data")
        if sub == SYMBOL_TOPIC:
            # 価格のキーはUI実装に依存するため、代表的なキーを探す
            if isinstance(payload, dict):
                price = payload.get("price") or payload.get("p") or payload.get("last")
                amount = payload.get("amount") or payload.get("qty") or payload.get("q")
            elif isinstance(payload, list) and payload:
                item = payload[0]
                if isinstance(item, dict):
                    price = item.get("price") or item.get("p") or item.get("last")
                    amount = item.get("amount") or item.get("qty") or item.get("q")
                else:
                    price = None
                    amount = None
            else:
                price = None
                amount = None
            if price is not None:
                last_price = price
                last_amount = amount
                last_topic = sub
        # 20秒おきにタイムスタンプで書き出しはタイマー側で行うため、ここでは保持のみ

        # 終了要求チェック
        if stop.is_set():
            break

    return last_price, last_amount, last_topic

async def ticker_writer(get_latest, interval):
    # 周期的にCSVへ書き込む
    while not stop.is_set():
        price, amount, topic = get_latest()
        if price is not None:
            ts = datetime.now(timezone.utc).isoformat()
            await log_price([ts, price, amount, topic])
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass

async def run():
    await ensure_header(CSV_FILE)

    # 共有状態
    state = {"price": None, "amount": None, "topic": None}

    def get_latest():
        return state["price"], state["amount"], state["topic"]

    while not stop.is_set():
        try:
            async with websockets.connect(WS) as ws:
                # 購読
                await ws.send(json.dumps({"cmd": "sub", "msg": SYMBOL_TOPIC}))

                writer_task = asyncio.create_task(ticker_writer(get_latest, INTERVAL_SEC))

                try:
                    async for msg in ws:
                        try:
                            data = json.loads(msg)
                        except json.JSONDecodeError:
                            continue
                        if data.get("sub") == SYMBOL_TOPIC:
                            payload = data.get("data")
                            price = None
                            amount = None
                            if isinstance(payload, dict):
                                price = payload.get("price") or payload.get("p") or payload.get("last")
                                amount = payload.get("amount") or payload.get("qty") or payload.get("q")
                            elif isinstance(payload, list) and payload:
                                item = payload[0]
                                if isinstance(item, dict):
                                    price = item.get("price") or item.get("p") or item.get("last")
                                    amount = item.get("amount") or item.get("qty") or item.get("q")
                            if price is not None:
                                state["price"] = price
                                state["amount"] = amount
                                state["topic"] = SYMBOL_TOPIC
                        if stop.is_set():
                            break
                finally:
                    writer_task.cancel()
                    try:
                        await writer_task
                    except:
                        pass
        except Exception:
            # 再接続待ち
            try:
                await asyncio.wait_for(stop.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

if __name__ == "__main__":
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, handle_sig)
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
