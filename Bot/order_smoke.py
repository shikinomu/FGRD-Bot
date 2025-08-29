from __future__ import annotations
import time
import yaml
from pathlib import Path
from exchanges.fgrd import FGRDClient, FGRDConfig


def load_client() -> FGRDClient:
    cfg = yaml.safe_load((Path(__file__).parent / 'config.yaml').read_text())
    f = cfg['exchanges']['fgrd']
    return FGRDClient(FGRDConfig(
        base_url=f.get('base_url', 'https://api.fgrcbit.com'),
        api_key=f.get('api_key', ''),
        api_secret=f.get('api_secret', ''),
        bearer_token=f.get('bearer_token', ''),
        cookie=f.get('cookie', ''),
    ))


def main() -> None:
    client = load_client()
    symbol = 'BTC'
    side = 1  # buy/long
    price = '105000'
    amount = 1
    lever_rate = 25

    print('Placing limit order:', dict(symbol=symbol, side=side, price=price, amount=amount, lever_rate=lever_rate))
    resp = client.create_limit_order(symbol=symbol, side=side, price=price, amount=amount, lever_rate=lever_rate, order_type=1)
    print('openPosition resp:', str(resp)[:400])

    # poll getCurrentEntrust for entrust_id
    entrust_id = None
    for _ in range(10):
        lst = client.get_current_entrust(page=1)
        items = (lst or {}).get('data', {}).get('data', [])
        if items:
            # find matching order by price/side/symbol and status unsold
            for it in items:
                if str(it.get('symbol')) == symbol and int(it.get('side', 0)) == side and str(it.get('entrust_price')) == str(price) and int(it.get('status', 0)) == 1:
                    entrust_id = it.get('id') or it.get('entrust_id')
                    break
            if entrust_id:
                break
        time.sleep(1)

    print('Sleeping 20s before cancel... (entrust_id=%s)' % entrust_id)
    time.sleep(20)

    print('Canceling order...')
    if entrust_id is not None:
        cresp = client.cancel_order(entrust_id=entrust_id, symbol=symbol)
    else:
        cresp = {'error': 'entrust_id not found'}
    print('cancel resp:', str(cresp)[:400])


if __name__ == '__main__':
    main()


