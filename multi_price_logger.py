import asyncio
import csv
import json
from datetime import datetime, timezone
import signal
import sys
from typing import Dict, Any, Optional

import websockets

# 現物は ws1、契約は ws2
WS_SPOT = "wss://api.fgrcbit.com/ws1"
WS_SWAP = "wss://api.fgrcbit.com/ws2"

# 記録対象: 現物(btcusdt)と契約(btc)の板(最良買/最良売)とラスト価格
SPOT_SYMBOL = "btcusdt"  # 現物は小文字
SWAP_BASE_UPPER = "BTC"  # 契約は大文字

CSV_FILE = "orderbook_last_10s.csv"
INTERVAL_SEC = 10

HEADER = [
    "timestamp",
    "market_type",  # spot or swap
    "symbol",       # btcusdt or btc
    "best_bid_price",
    "best_ask_price",
    "last_price",
]

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

class MarketState:
    def __init__(self):
        self.best_bid_price: Optional[float] = None
        self.best_ask_price: Optional[float] = None
        self.last_price: Optional[float] = None

spot_state = MarketState()
swap_state = MarketState()

# 受信メッセージの解析（UI実装に合わせたtopic形式）
# - 板: buyList_<symbol>, sellList_<symbol>, swapBuyList_<base>, swapSellList_<base>
# - ラスト: tradeList_<symbol>, swapTradeList_<base>

def parse_price(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None

async def handle_message(msg: str):
    try:
        data = json.loads(msg)
    except Exception:
        return

    topic = data.get("sub") or data.get("topic") or data.get("msg")
    payload = data.get("data")

    if not topic or payload is None:
        return

    # 板: payload は配列の可能性が高い。最良のみを抽出
    # 期待形式: [[price, amount], ...] あるいは dict の配列
    def extract_best(entries):
        best_price = None
        if isinstance(entries, list) and entries:
            first = entries[0]
            if isinstance(first, list) and len(first) >= 1:
                best_price = parse_price(first[0])
            elif isinstance(first, dict):
                # {price: xxx} 形式を想定
                best_price = parse_price(first.get("price"))
        return best_price

    # ラスト: payload が {price: x} あるいは配列の先頭に価格
    def extract_last(entry):
        if isinstance(entry, dict):
            return parse_price(entry.get("price"))
        if isinstance(entry, list) and entry:
            return parse_price(entry[0])
        return None

    # 現物の板/約定
    if topic == f"buyList_{SPOT_SYMBOL}":
        spot_state.best_bid_price = extract_best(payload)
    elif topic == f"sellList_{SPOT_SYMBOL}":
        spot_state.best_ask_price = extract_best(payload)
    elif topic == f"tradeList_{SPOT_SYMBOL}":
        # 約定配列の先頭をラストとみなす
        if isinstance(payload, list) and payload:
            spot_state.last_price = extract_last(payload[0])
        else:
            spot_state.last_price = extract_last(payload)

    # 契約の板/約定（大文字シンボル）
    elif topic == f"swapBuyList_{SWAP_BASE_UPPER}":
        swap_state.best_bid_price = extract_best(payload)
    elif topic == f"swapSellList_{SWAP_BASE_UPPER}":
        swap_state.best_ask_price = extract_best(payload)
    elif topic == f"swapTradeList_{SWAP_BASE_UPPER}":
        if isinstance(payload, list) and payload:
            swap_state.last_price = extract_last(payload[0])
        else:
            swap_state.last_price = extract_last(payload)

async def writer_loop():
    await ensure_header(CSV_FILE)
    while not stop.is_set():
        now = datetime.now(timezone.utc).isoformat()
        # 現物
        with open(CSV_FILE, "a", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                now, "spot", SPOT_SYMBOL,
                spot_state.best_bid_price, spot_state.best_ask_price, spot_state.last_price
            ])
            # 契約
            w.writerow([
                now, "swap", SWAP_BASE_UPPER,
                swap_state.best_bid_price, swap_state.best_ask_price, swap_state.last_price
            ])
        try:
            await asyncio.wait_for(stop.wait(), timeout=INTERVAL_SEC)
        except asyncio.TimeoutError:
            pass

async def ws_loop_spot():
    # 現物（ws1）
    while not stop.is_set():
        try:
            async with websockets.connect(WS_SPOT, ping_interval=20, ping_timeout=20) as ws:
                subs = [
                    {"cmd":"sub","msg":f"buyList_{SPOT_SYMBOL}"},
                    {"cmd":"sub","msg":f"sellList_{SPOT_SYMBOL}"},
                    {"cmd":"sub","msg":f"tradeList_{SPOT_SYMBOL}"},
                ]
                for s in subs:
                    await ws.send(json.dumps(s))

                async for msg in ws:
                    await handle_message(msg)
        except Exception:
            await asyncio.sleep(2)

async def ws_loop_swap():
    # 契約（ws2, 大文字シンボル）
    while not stop.is_set():
        try:
            async with websockets.connect(WS_SWAP, ping_interval=20, ping_timeout=20) as ws:
                subs = [
                    {"cmd":"sub","msg":f"swapBuyList_{SWAP_BASE_UPPER}"},
                    {"cmd":"sub","msg":f"swapSellList_{SWAP_BASE_UPPER}"},
                    {"cmd":"sub","msg":f"swapTradeList_{SWAP_BASE_UPPER}"},
                ]
                for s in subs:
                    await ws.send(json.dumps(s))

                async for msg in ws:
                    await handle_message(msg)
        except Exception:
            await asyncio.sleep(2)

async def main():
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_sig)
    await asyncio.gather(ws_loop_spot(), ws_loop_swap(), writer_loop())

if __name__ == "__main__":
    asyncio.run(main())
