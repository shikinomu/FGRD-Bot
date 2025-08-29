from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any
from pathlib import Path
import csv
import time

from .signals import SpreadSignals


@dataclass
class EngineState:
    mode: str = 'IDLE'
    opened_ts: float | None = None


class Engine:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.state = EngineState()
        self.signals = SpreadSignals(config)
        self.journal_path = Path('/Users/yoshinorinomura/Desktop/private/FGRD/Bot/trade_journal.csv')
        if not self.journal_path.exists():
            with open(self.journal_path, 'w', newline='') as f:
                csv.writer(f).writerow(['ts','event','mode','spread','size_btc'])

    def start(self) -> None:
        pass

    def tick(self) -> None:
        dp = self.signals.next_datapoint()
        if dp is None:
            return
        spread = dp['spread_main']
        if self.state.mode == 'IDLE':
            if self.signals.should_enter(spread):
                size_btc = self._decide_size()
                self._log('enter', spread, size_btc)
                self.state.mode = 'OPEN'
                self.state.opened_ts = dp['ts']
        else:
            if self.signals.should_exit(spread, self.state.opened_ts, dp['ts']):
                self._log('exit', spread, 0.0)
                self.state.mode = 'IDLE'
                self.state.opened_ts = None

    def stop(self) -> None:
        pass

    def _decide_size(self) -> float:
        # quantities are not present in compare_10s.csv; fallback to config
        max_pos = float(self.config['risk']['max_pos_btc'])
        # future: compute from best qtys and leverage/margin
        return max_pos

    def _log(self, event: str, spread: float, size_btc: float) -> None:
        with open(self.journal_path, 'a', newline='') as f:
            csv.writer(f).writerow([time.time(), event, self.state.mode, f"{spread:.6f}", f"{size_btc:.6f}"])
