import asyncio, json, time
import websockets

URL = "wss://api.fgrcbit.com/ws1"
SUBS = [
    {"cmd":"sub","msg":"exchangeMarketList"},
    {"cmd":"sub","msg":"swapMarketList"},
]

async def main():
    async with websockets.connect(URL) as ws:
        for s in SUBS:
            await ws.send(json.dumps(s))
        start = time.time()
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
            if topic in ("exchangeMarketList", "swapMarketList"):
                print(topic, "len=", (len(payload) if isinstance(payload, list) else 'dict'))
                # プレビュー
                if isinstance(payload, list) and payload:
                    print("sample:", str(payload[0])[:200])
                elif isinstance(payload, dict):
                    print("keys:", list(payload.keys())[:10])

if __name__ == '__main__':
    asyncio.run(main())
