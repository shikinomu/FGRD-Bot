import asyncio, csv, json, signal, time
from datetime import datetime, timezone
import websockets

WS = "wss://api.fgrcbit.com/ws1"
SYMBOL = "btcusdt"
CSV = "spot_orderbook_10s.csv"
INTERVAL = 10

best_bid = None
best_ask = None
last_price = None
stop = asyncio.Event()

def handle_sig(*_):
    stop.set()

async def ensure_header():
    try:
        with open(CSV, "x", newline="") as f:
            csv.writer(f).writerow(["timestamp","best_bid","best_ask","last_price"]) 
    except FileExistsError:
        pass

async def writer():
    await ensure_header()
    last_bucket = None
    while not stop.is_set():
        now = time.time()
        bucket = int(now // INTERVAL)
        if bucket != last_bucket:
            with open(CSV, "a", newline="") as f:
                csv.writer(f).writerow([
                    datetime.now(timezone.utc).isoformat(), best_bid, best_ask,
                    (last_price if last_price is not None else (
                        (best_bid + best_ask)/2 if (best_bid is not None and best_ask is not None) else None
                    ))
                ])
            last_bucket = bucket
        await asyncio.sleep(0.5)

async def consumer():
    while not stop.is_set():
        try:
            async with websockets.connect(WS, ping_interval=20, ping_timeout=20) as ws:
                for m in (
                    {"cmd":"sub","msg":f"buyList_{SYMBOL}"},
                    {"cmd":"sub","msg":f"sellList_{SYMBOL}"},
                    {"cmd":"sub","msg":f"tradeList_{SYMBOL}"},
                ):
                    await ws.send(json.dumps(m))
                async for msg in ws:
                    try:
                        data = json.loads(msg)
                        topic = data.get("sub") or data.get("topic") or data.get("msg")
                        payload = data.get("data")
                        if not topic or payload is None:
                            continue
                        global best_bid, best_ask, last_price
                        if topic == f"buyList_{SYMBOL}":
                            if isinstance(payload, list) and payload:
                                row = payload[0]
                                best_bid = float(row[0] if isinstance(row, list) else row.get("price"))
                        elif topic == f"sellList_{SYMBOL}":
                            if isinstance(payload, list) and payload:
                                row = payload[0]
                                best_ask = float(row[0] if isinstance(row, list) else row.get("price"))
                        elif topic == f"tradeList_{SYMBOL}":
                            if isinstance(payload, list) and payload:
                                item = payload[0]
                                last_price = float(item[0] if isinstance(item, list) else item.get("price"))
                    except Exception:
                        continue
        except Exception:
            await asyncio.sleep(2)

async def main():
    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(s, handle_sig)
    await asyncio.gather(consumer(), writer())

if __name__ == "__main__":
    asyncio.run(main())
