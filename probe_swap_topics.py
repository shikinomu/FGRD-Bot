import asyncio, json, time
import websockets

URL = "wss://api.fgrcbit.com/ws1"
CANDIDATES = [
    ("swapBuyList_btc", {"cmd":"sub","msg":"swapBuyList_btc"}),
    ("swapSellList_btc", {"cmd":"sub","msg":"swapSellList_btc"}),
    ("swapTradeList_btc", {"cmd":"sub","msg":"swapTradeList_btc"}),
    ("swapBuyList_btcusdt", {"cmd":"sub","msg":"swapBuyList_btcusdt"}),
    ("swapSellList_btcusdt", {"cmd":"sub","msg":"swapSellList_btcusdt"}),
    ("swapTradeList_btcusdt", {"cmd":"sub","msg":"swapTradeList_btcusdt"}),
]

async def main():
    async with websockets.connect(URL) as ws:
        for _, s in CANDIDATES:
            await ws.send(json.dumps(s))
        start = time.time()
        hits = {}
        while time.time() - start < 12:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2)
            except Exception:
                continue
            try:
                data = json.loads(msg)
            except Exception:
                continue
            topic = data.get("sub") or data.get("topic") or data.get("msg")
            payload = data.get("data")
            if not topic or payload is None:
                continue
            preview = None
            if isinstance(payload, list) and payload:
                preview = payload[0]
            elif isinstance(payload, dict):
                preview = list(payload.keys())[:3]
            print(f"HIT {topic}: {str(preview)[:120]}")
            hits[topic] = True
        print("\nSummary:")
        for name, _ in CANDIDATES:
            print(f"{name}: {'OK' if hits.get(name) else 'NO'}")

if __name__ == '__main__':
    asyncio.run(main())
