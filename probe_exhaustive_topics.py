import asyncio, json, time, itertools
import websockets

URL = "wss://api.fgrcbit.com/ws1"

prefixes = ["swap", "contract", "futures", "perp"]
list_types = ["BuyList", "SellList", "TradeList", "buyList", "sellList", "tradeList"]
symbols = ["btc", "btcusdt", "BTC", "BTCUSDT", "btc_usdt", "BTC_USDT"]

# also try generic topics
generics = [
    "swapMarketList", "contractMarketList", "futuresMarketList",
    "ticker_btcusdt", "ticker_btc", "Ticker_btcusdt", "Ticker_btc",
]

subs = []
for p, lt, sym in itertools.product(prefixes, list_types, symbols):
    topic = f"{p}{lt}_{sym}"
    subs.append({"cmd":"sub","msg":topic})
# also try without underscore
for p, lt, sym in itertools.product(prefixes, list_types, symbols):
    topic = f"{p}{lt}{sym}"
    subs.append({"cmd":"sub","msg":topic})
# add generics
for g in generics:
    subs.append({"cmd":"sub","msg":g})

async def main():
    async with websockets.connect(URL) as ws:
        for s in subs:
            await ws.send(json.dumps(s))
        start = time.time()
        hits = {}
        while time.time() - start < 15:
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
            if topic not in hits:
                preview = None
                if isinstance(payload, list) and payload:
                    preview = payload[0]
                elif isinstance(payload, dict):
                    preview = list(payload.keys())[:3]
                print(f"HIT {topic}: {str(preview)[:160]}")
                hits[topic] = True
        print("\nTotal hits:", len(hits))

if __name__ == '__main__':
    asyncio.run(main())
