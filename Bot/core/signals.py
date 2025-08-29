from __future__ import annotations
from typing import Dict, Any, Optional
from pathlib import Path
import csv
import time
import json


class SpreadSignals:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.cfg = config
        # strategy rules (JSON)
        rules_path = Path(__file__).resolve().parents[1] / 'strategy_rules.json'
        if rules_path.exists():
            rules = json.loads(rules_path.read_text())
            self.enter_band = float(rules['entry']['threshold'])
            self.entry_hits_need = int(rules['entry'].get('consecutive', 2))
            self.exit_band = float(rules['exit']['take_profit']['threshold'])
            self.exit_hits_need = int(rules['exit']['take_profit'].get('consecutive', 3))
            self.stop_band = float(rules['exit']['stop_loss']['threshold'])
            self.stop_hits_need = int(rules['exit']['stop_loss'].get('consecutive', 3))
            self.min_hold = float(rules['exit']['min_hold_sec'])
            self.max_hold = float(rules['exit']['max_hold_sec'])
        else:
            # fallback to config.yaml values
            self.enter_band = float(self.cfg['signals']['enter_band_usd'])
            self.entry_hits_need = int(self.cfg['signals'].get('persistence_n', 2))
            self.exit_band  = float(self.cfg['signals']['exit_band_low_usd'])
            self.exit_hits_need = 2
            self.stop_band  = float(self.cfg['risk']['stop_band_usd'])
            self.stop_hits_need = 2
            self.min_hold = 0.0
            self.max_hold   = float(self.cfg['signals']['max_hold_sec'])
        self._csv_path = Path('/Users/yoshinorinomura/Desktop/private/FGRD/compare_10s.csv')
        self._it = None
        if self._csv_path.exists():
            self._it = self._iter_csv(self._csv_path)
        self._entry_hits = 0
        self._tp_hits = 0
        self._sl_hits = 0

    def _iter_csv(self, path: Path):
        with open(path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    # headers in compare_10s.csv
                    # timestamp, ..., swap_fgrd_bid, swap_fgrd_ask, ..., swap_bybit_bid, swap_bybit_ask, ...
                    fb = float(row.get('swap_fgrd_bid') or 'nan')
                    ba = float(row.get('swap_bybit_ask') or 'nan')
                except ValueError:
                    continue
                if any(map(lambda x: x != x, [fb, ba])):
                    continue
                spread_main = fb - ba
                yield {'ts': time.time(), 'spread_main': spread_main}

    def next_datapoint(self) -> Optional[Dict[str, Any]]:
        if self._it is None:
            return None
        try:
            return next(self._it)
        except StopIteration:
            return None

    def should_enter(self, spread: float) -> bool:
        if abs(spread) <= self.enter_band:
            self._entry_hits += 1
        else:
            self._entry_hits = 0
        if self._entry_hits >= self.entry_hits_need:
            self._entry_hits = 0
            # reset exit counters on open
            self._tp_hits = 0
            self._sl_hits = 0
            return True
        return False

    def should_exit(self, spread: float, opened_ts: float | None, now_ts: float) -> bool:
        if opened_ts is None:
            return False
        held = now_ts - opened_ts
        if held < self.min_hold:
            # do not accumulate hits during min_hold
            self._tp_hits = 0
            self._sl_hits = 0
            return False
        # time-based exit
        if held >= self.max_hold:
            self._tp_hits = 0
            self._sl_hits = 0
            return True
        # price-based exits with consecutive hits
        if spread >= self.exit_band:
            self._tp_hits += 1
        else:
            self._tp_hits = 0
        if spread <= self.stop_band:
            self._sl_hits += 1
        else:
            self._sl_hits = 0
        if self._tp_hits >= self.exit_hits_need or self._sl_hits >= self.stop_hits_need:
            self._tp_hits = 0
            self._sl_hits = 0
            return True
        return False
