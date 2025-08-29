import asyncio, json, time
import websockets

URLS = ["wss://api.fgrcbit.com/ws1", "wss://api.fgrcbit.com/ws2"]
TOPICS = [
    {"cmd":"sub","msg":"swapTradeList_BTC"},
    {"cmd":"sub","msg":"swapBuyList_BTC"},
    {"cmd":"sub","msg":"swapSellList_BTC"},
]

async def probe(url):
    print("--", url)
    try:
        async with websockets.connect(url) as ws:
            for s in TOPICS:
                await ws.send(json.dumps(s))
            start = time.time()
            hits = 0
            while time.time() - start < 6:
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
                if topic and payload is not None:
                    print("HIT", topic, str(payload)[:120])
                    hits += 1
            print("hits:", hits)
    except Exception as e:
        print("err", e)

async def main():
    for u in URLS:
        await probe(u)

asyncio.run(main())
