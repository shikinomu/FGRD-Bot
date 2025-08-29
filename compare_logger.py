import asyncio, csv, json, signal
from datetime import datetime, timezone
import websockets

# FGRD
FGRD_WS_SPOT = "wss://api.fgrcbit.com/ws1"
FGRD_WS_SWAP = "wss://api.fgrcbit.com/ws2"
FGRD_SPOT = "btcusdt"
FGRD_SWAP = "BTC"  # 大文字

# Bybit v5 public
BYBIT_WS_SPOT = "wss://stream.bybit.com/v5/public/spot"
BYBIT_WS_LINEAR = "wss://stream.bybit.com/v5/public/linear"  # USDT無期限
BYBIT_SYMBOL = "BTCUSDT"

CSV = "compare_10s.csv"
INTERVAL = 10

# State holders
spot_fgrd_bid = None
spot_fgrd_ask = None
spot_fgrd_last = None

swap_fgrd_bid = None
swap_fgrd_ask = None
swap_fgrd_last = None

spot_bybit_bid = None
spot_bybit_ask = None
spot_bybit_last = None

swap_bybit_bid = None
swap_bybit_ask = None
swap_bybit_last = None

stop = asyncio.Event()

def handle_sig(*_):
    stop.set()

async def ensure_header():
    try:
        with open(CSV, "x", newline="") as f:
            csv.writer(f).writerow([
                "timestamp",
                "spot_fgrd_bid","spot_fgrd_ask","spot_fgrd_last",
                "spot_bybit_bid","spot_bybit_ask","spot_bybit_last",
                "swap_fgrd_bid","swap_fgrd_ask","swap_fgrd_last",
                "swap_bybit_bid","swap_bybit_ask","swap_bybit_last",
            ])
    except FileExistsError:
        pass

async def writer_loop():
    global spot_fgrd_last, swap_fgrd_last, spot_bybit_last, swap_bybit_last
    await ensure_header()
    while not stop.is_set():
        # last のフォールバック: 中値
        sfl = spot_fgrd_last if spot_fgrd_last is not None else (
            (spot_fgrd_bid + spot_fgrd_ask)/2 if (spot_fgrd_bid is not None and spot_fgrd_ask is not None) else None
        )
        swfl = swap_fgrd_last if swap_fgrd_last is not None else (
            (swap_fgrd_bid + swap_fgrd_ask)/2 if (swap_fgrd_bid is not None and swap_fgrd_ask is not None) else None
        )
        sbl = spot_bybit_last if spot_bybit_last is not None else (
            (spot_bybit_bid + spot_bybit_ask)/2 if (spot_bybit_bid is not None and spot_bybit_ask is not None) else None
        )
        swbl = swap_bybit_last if swap_bybit_last is not None else (
            (swap_bybit_bid + swap_bybit_ask)/2 if (swap_bybit_bid is not None and swap_bybit_ask is not None) else None
        )
        with open(CSV, "a", newline="") as f:
            csv.writer(f).writerow([
                datetime.now(timezone.utc).isoformat(),
                spot_fgrd_bid, spot_fgrd_ask, sfl,
                spot_bybit_bid, spot_bybit_ask, sbl,
                swap_fgrd_bid, swap_fgrd_ask, swfl,
                swap_bybit_bid, swap_bybit_ask, swbl,
            ])
        try:
            await asyncio.wait_for(stop.wait(), timeout=INTERVAL)
        except asyncio.TimeoutError:
            pass

async def fgrd_spot_loop():
    global spot_fgrd_bid, spot_fgrd_ask, spot_fgrd_last
    while not stop.is_set():
        try:
            async with websockets.connect(FGRD_WS_SPOT, ping_interval=20, ping_timeout=20) as ws:
                for m in (
                    {"cmd":"sub","msg":f"buyList_{FGRD_SPOT}"},
                    {"cmd":"sub","msg":f"sellList_{FGRD_SPOT}"},
                    {"cmd":"sub","msg":f"tradeList_{FGRD_SPOT}"},
                ):
                    await ws.send(json.dumps(m))
                async for msg in ws:
                    try:
                        data = json.loads(msg)
                        topic = data.get("sub") or data.get("topic") or data.get("msg")
                        payload = data.get("data")
                        if not topic or payload is None:
                            continue
                        if topic == f"buyList_{FGRD_SPOT}":
                            if isinstance(payload, list) and payload:
                                row = payload[0]
                                spot_fgrd_bid = float(row[0] if isinstance(row, list) else row.get("price"))
                        elif topic == f"sellList_{FGRD_SPOT}":
                            if isinstance(payload, list) and payload:
                                row = payload[0]
                                spot_fgrd_ask = float(row[0] if isinstance(row, list) else row.get("price"))
                        elif topic == f"tradeList_{FGRD_SPOT}":
                            if isinstance(payload, list) and payload:
                                item = payload[0]
                                spot_fgrd_last = float(item[0] if isinstance(item, list) else item.get("price"))
                    except Exception:
                        continue
        except Exception:
            await asyncio.sleep(2)

async def fgrd_swap_loop():
    global swap_fgrd_bid, swap_fgrd_ask, swap_fgrd_last
    while not stop.is_set():
        try:
            async with websockets.connect(FGRD_WS_SWAP, ping_interval=20, ping_timeout=20) as ws:
                for m in (
                    {"cmd":"sub","msg":f"swapBuyList_{FGRD_SWAP}"},
                    {"cmd":"sub","msg":f"swapSellList_{FGRD_SWAP}"},
                    {"cmd":"sub","msg":f"swapTradeList_{FGRD_SWAP}"},
                ):
                    await ws.send(json.dumps(m))
                async for msg in ws:
                    try:
                        data = json.loads(msg)
                        topic = data.get("sub") or data.get("topic") or data.get("msg")
                        payload = data.get("data")
                        if not topic or payload is None:
                            continue
                        if topic == f"swapBuyList_{FGRD_SWAP}":
                            if isinstance(payload, list) and payload:
                                row = payload[0]
                                swap_fgrd_bid = float(row[0] if isinstance(row, list) else row.get("price"))
                        elif topic == f"swapSellList_{FGRD_SWAP}":
                            if isinstance(payload, list) and payload:
                                row = payload[0]
                                swap_fgrd_ask = float(row[0] if isinstance(row, list) else row.get("price"))
                        elif topic == f"swapTradeList_{FGRD_SWAP}":
                            if isinstance(payload, dict) and payload.get("price") is not None:
                                swap_fgrd_last = float(payload.get("price"))
                            elif isinstance(payload, list) and payload:
                                item = payload[0]
                                swap_fgrd_last = float(item[0] if isinstance(item, list) else item.get("price"))
                    except Exception:
                        continue
        except Exception:
            await asyncio.sleep(2)

async def bybit_spot_loop():
    global spot_bybit_bid, spot_bybit_ask, spot_bybit_last
    while not stop.is_set():
        try:
            async with websockets.connect(BYBIT_WS_SPOT, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(json.dumps({"op":"subscribe", "args":[f"tickers.{BYBIT_SYMBOL}"]}))
                await ws.send(json.dumps({"op":"subscribe", "args":[f"orderbook.1.{BYBIT_SYMBOL}"]}))
                async for msg in ws:
                    try:
                        data = json.loads(msg)
                        # heartbeat
                        if data.get("op") == "ping":
                            await ws.send(json.dumps({"op":"pong"}))
                            continue
                        topic = data.get("topic", "")
                        if topic.startswith("tickers") and data.get("data"):
                            arr = data["data"]
                            d0 = None
                            if isinstance(arr, list) and arr:
                                d0 = arr[0]
                            elif isinstance(arr, dict):
                                d0 = arr
                            if d0 and d0.get("symbol") == BYBIT_SYMBOL:
                                # fields are strings
                                if d0.get("lastPrice"):
                                    spot_bybit_last = float(d0.get("lastPrice"))
                                # bid/ask はエンドポイントによってキーが異なることがある
                                if d0.get("bid1Price") or d0.get("bestBidPrice"):
                                    spot_bybit_bid = float(d0.get("bid1Price"))
                                if d0.get("ask1Price") or d0.get("bestAskPrice"):
                                    spot_bybit_ask = float(d0.get("ask1Price"))
                        elif topic.startswith("orderbook.1") and data.get("data"):
                            d0 = data["data"]
                            # d0: { "s":symbol, "b":[[price, size],...], "a":[[price, size],...] }
                            try:
                                if d0.get("b"):
                                    spot_bybit_bid = float(d0["b"][0][0])
                                if d0.get("a"):
                                    spot_bybit_ask = float(d0["a"][0][0])
                            except Exception:
                                pass
                    except Exception:
                        continue
        except Exception:
            await asyncio.sleep(2)

async def bybit_linear_loop():
    global swap_bybit_bid, swap_bybit_ask, swap_bybit_last
    while not stop.is_set():
        try:
            async with websockets.connect(BYBIT_WS_LINEAR, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(json.dumps({"op":"subscribe", "args":[f"tickers.{BYBIT_SYMBOL}"]}))
                await ws.send(json.dumps({"op":"subscribe", "args":[f"orderbook.1.{BYBIT_SYMBOL}"]}))
                async for msg in ws:
                    try:
                        data = json.loads(msg)
                        # heartbeat
                        if data.get("op") == "ping":
                            await ws.send(json.dumps({"op":"pong"}))
                            continue
                        topic = data.get("topic", "")
                        if topic.startswith("tickers") and data.get("data"):
                            arr = data["data"]
                            d0 = None
                            if isinstance(arr, list) and arr:
                                d0 = arr[0]
                            elif isinstance(arr, dict):
                                d0 = arr
                            if d0 and d0.get("symbol") == BYBIT_SYMBOL:
                                if d0.get("lastPrice"):
                                    swap_bybit_last = float(d0.get("lastPrice"))
                                if d0.get("bid1Price") or d0.get("bestBidPrice"):
                                    swap_bybit_bid = float(d0.get("bid1Price"))
                                if d0.get("ask1Price") or d0.get("bestAskPrice"):
                                    swap_bybit_ask = float(d0.get("ask1Price"))
                        elif topic.startswith("orderbook.1") and data.get("data"):
                            d0 = data["data"]
                            try:
                                if d0.get("b"):
                                    swap_bybit_bid = float(d0["b"][0][0])
                                if d0.get("a"):
                                    swap_bybit_ask = float(d0["a"][0][0])
                            except Exception:
                                pass
                    except Exception:
                        continue
        except Exception:
            await asyncio.sleep(2)

async def main():
    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(s, handle_sig)
    await asyncio.gather(
        writer_loop(),
        fgrd_spot_loop(), fgrd_swap_loop(),
        bybit_spot_loop(), bybit_linear_loop(),
    )

if __name__ == "__main__":
    asyncio.run(main())
