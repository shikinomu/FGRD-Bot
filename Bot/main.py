from __future__ import annotations
import time
import yaml
from pathlib import Path

from core.engine import Engine


def load_config(path: str | Path) -> dict:
    with open(path, 'r') as f:
        return yaml.safe_load(f)


def main() -> None:
    cfg = load_config(Path(__file__).parent / 'config.yaml')
    engine = Engine(cfg)
    try:
        engine.start()
        while True:
            engine.tick()
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()


if __name__ == '__main__':
    main()
