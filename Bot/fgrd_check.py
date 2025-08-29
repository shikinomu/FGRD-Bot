from __future__ import annotations
from pathlib import Path
import yaml
from exchanges.fgrd import FGRDClient, FGRDConfig


def load_cfg():
    cfg = yaml.safe_load((Path(__file__).parent / 'config.yaml').read_text())
    f = cfg['exchanges']['fgrd']
    return FGRDConfig(base_url=f.get('base_url', ''), api_key=f.get('api_key', ''), api_secret=f.get('api_secret', ''))


def main() -> None:
    cfg = load_cfg()
    client = FGRDClient(cfg)
    try:
        print('balances:', client.get_balances())
    except Exception as e:
        print('balances_error:', e)
    try:
        print('positions:', client.get_positions('BTCUSDT'))
    except Exception as e:
        print('positions_error:', e)
    try:
        print('fund_account:', client.get_fund_account())
    except Exception as e:
        print('fund_account_error:', e)


if __name__ == '__main__':
    main()


