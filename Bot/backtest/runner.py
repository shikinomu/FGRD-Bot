from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import csv
from typing import List, Dict, Any
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import json


@dataclass
class Config:
    enter_band: float
    exit_band: float
    stop_band: float
    persistence_n: int
    max_hold_sec: float
    min_hold_sec: float
    taker_fee: float
    slippage_usd: float
    unit_btc: float

    @staticmethod
    def from_rules_json(path: Path, taker_fee: float, slippage_usd: float, unit_btc: float) -> 'Config':
        data = json.loads(Path(path).read_text())
        enter = data['entry']
        exitc = data['exit']
        return Config(
            enter_band=float(enter['threshold']),
            exit_band=float(exitc['take_profit']['threshold']),
            stop_band=float(exitc['stop_loss']['threshold']),
            persistence_n=int(enter.get('consecutive', 2)),
            max_hold_sec=float(exitc['max_hold_sec']),
            min_hold_sec=float(exitc['min_hold_sec']),
            taker_fee=float(taker_fee),
            slippage_usd=float(slippage_usd),
            unit_btc=float(unit_btc),
        )


def load_rows(csv_path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                fb = float(r.get('swap_fgrd_bid') or 'nan')
                ba = float(r.get('swap_bybit_ask') or 'nan')
            except ValueError:
                continue
            if fb != fb or ba != ba:
                continue
            rows.append({'ts': r.get('timestamp'), 'spread': fb - ba})
    return rows


def run_backtest(rows: List[Dict[str, Any]], cfg: Config) -> Dict[str, Any]:
    trades: List[Dict[str, Any]] = []
    state = 'FLAT'
    entry_hits = 0
    exit_hits = 0
    entry_idx = None
    entry_spread = None
    pnl = 0.0

    for i, row in enumerate(rows):
        s = row['spread']
        if state == 'FLAT':
            entry_hits = entry_hits + 1 if abs(s) <= cfg.enter_band else 0
            if entry_hits >= 2:  # 2 consecutive hits for entry
                state = 'OPEN'
                entry_idx = i
                entry_spread = s
                trades.append({'ts': row['ts'], 'side': 'long_spread', 'type': 'entry', 'spread': s, 'i': i})
                exit_hits = 0
        else:
            held = (i - (entry_idx or i)) * 10.0
            # enforce minimum hold time before any exit condition
            if held < cfg.min_hold_sec:
                continue
            # price-based exit lines require 3 consecutive hits
            price_exit = (s >= cfg.exit_band) or (s <= cfg.stop_band)
            exit_hits = exit_hits + 1 if price_exit else 0
            time_exit = held >= cfg.max_hold_sec
            if (price_exit and exit_hits >= 3) or time_exit:
                raw = (s - (entry_spread or s))
                cost = 2.0 * cfg.taker_fee * 1.0 + cfg.slippage_usd
                pnl += raw - cost
                trades.append({'ts': row['ts'], 'side': 'long_spread', 'type': 'exit', 'spread': s, 'raw': raw, 'pnl': pnl, 'i': i, 'pnl_cum': pnl})
                state = 'FLAT'
                entry_idx = None
                entry_spread = None
                entry_hits = 0
                exit_hits = 0

    # Build equity curve (step function updated on each exit)
    exit_map: Dict[int, float] = {t['i']: t['pnl_cum'] for t in trades if t['type'] == 'exit'}
    equity: List[Dict[str, Any]] = []
    current = 0.0
    for i, row in enumerate(rows):
        if i in exit_map:
            current = exit_map[i]
        equity.append({'ts': row['ts'], 'equity': current})

    return {
        'trades': trades,
        'equity': equity,
        'summary': {
            'pnl': pnl,
            'num_trades': sum(1 for t in trades if t['type']=='exit')
        }
    }


def write_outputs(out_dir: Path, result: Dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / 'trades.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=sorted({k for t in result['trades'] for k in t.keys()}))
        w.writeheader()
        for t in result['trades']:
            w.writerow(t)
    with open(out_dir / 'summary.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['pnl','num_trades'])
        w.writeheader()
        w.writerow(result['summary'])
    with open(out_dir / 'equity.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['ts','equity'])
        w.writeheader()
        for e in result['equity']:
            w.writerow(e)

def plot_spread_with_trades_and_equity(rows: List[Dict[str, Any]], result: Dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    x = list(range(len(rows)))
    y = [r['spread'] for r in rows]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 7), sharex=True, gridspec_kw={'height_ratios':[3,1]})
    ax1.plot(x, y, label='spread (FGRD bid - Bybit ask)')
    ax1.axhline(0, color='gray', ls=':')
    entries = [t for t in result['trades'] if t['type']=='entry']
    exits   = [t for t in result['trades'] if t['type']=='exit']
    ax1.scatter([t['i'] for t in entries], [t['spread'] for t in entries], color='green', s=30, label='entry')
    ax1.scatter([t['i'] for t in exits],   [t['spread'] for t in exits],   color='red',   s=30, label='exit')
    ax1.legend()
    # equity
    ex = list(range(len(result['equity'])))
    ey = [e['equity'] for e in result['equity']]
    ax2.plot(ex, ey, color='black', label='equity (cum PnL)')
    ax2.legend()
    fig.tight_layout()
    fig.savefig(out_dir / 'spread_trades_equity.png', dpi=150)
