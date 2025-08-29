## 目的
FGRD と Bybit の BTCUSDT 無期限契約における価格差（スプレッド）の短期回帰性を利用し、
ゼロ近傍でエントリ・平常帯回帰で利確する裁定トレーディングを自動化する。

## 範囲
- MVP はドライラン（実発注OFF）での自動判定・状態遷移・イベント記録まで
- 次段で最小ロットの実発注（Bybit片側→両側）へ拡張

## 用語/スプレッド定義
- spread_main = FGRD_bid − Bybit_ask（基準、青）
- spread_alt  = Bybit_bid − FGRD_ask（対称、橙、将来拡張）
- 平常帯: 実運用で動的再推定する帯域（例: +350〜+450USD）
- ゼロ帯: エントリ確認帯（例: |spread_main| ≤ 50〜100USD）
- 有効スプレッド: スプレッド − 取引コスト（両サイド taker + スリッページ）

## 仕様（機能要件）
1. データ取得/同期
   - 入力: 10秒バケットの `compare_10s.csv`（初期）→ 後にWS直結へ移行
   - フィールド: FGRD先物の best bid/ask、Bybit USDT perp の best bid/ask
   - 欠損補完: 直近値で前方補完、異常点はスキップ
2. シグナル生成
   - Entry: `|spread_main| ≤ enter_band` を `persistence_n` 回連続
   - Exit: `spread_main ≥ exit_band_low` or `t_hold ≥ max_hold_sec` or `spread_main ≤ stop_band`
   - 平常帯: SMA(window) + 分位/IQR で動的更新（MVPでは固定帯）
3. 状態遷移
   - `IDLE → OPEN → FLAT`、片張り検知 → 即ヘッジ/ABORT
4. 発注（インターフェース）
   - 両所同時: FGRDロング×Bybitショート（名目一致）、または逆方向
   - idempotency: clientOrderId を用意
   - リスク: 最大ポジ上限、逆行撤退帯、クールダウン
5. ロギング/監視
   - イベント（判定・発注・約定・PnL）CSV/Parquet出力
   - メトリクス: エントリ回数、勝率、平均滞在、PnL、DD（将来）

6. 執行/サイズ決定（追加）
   - 成行実行: エントリ/エグジットとも基本は at market（片張り回避を優先）
   - ロット上限: 直近10秒の最良気配数量のうち小さい方
     - `size_upper = min(FGRD_best_qty, Bybit_best_qty)` を上限
     - さらに `max_pos_btc` と利用可能証拠金（レバレッジ制約）でクリップ
   - 例外時: 板薄・拒否・急拡大スリッページ検知でクールダウン

## 仕様（非機能要件）
- 10秒粒度で 1s tick の軽量ループ
- フェイルセーフ: ネットワーク/約定エラー時の再試行・クールダウン
- 設定ホットリロード（将来）

## 設定パラメータ（config.yaml）
- symbols: perp
- sampling: interval_sec
- signals: enter_band_usd, persistence_n, exit_band_low_usd, exit_band_high_usd, max_hold_sec, dynamic_window_sec
- costs: taker_fee, slippage_usd
- risk: stop_band_usd, max_pos_btc
- exchanges: bybit(api_key, secret, base_url), fgrd(...)
- ops: log_level, dry_run

## API/アダプタ（概要）
- Bybit v5
  - REST: /v5/order/create, /v5/order/cancel, /v5/position/list, /v5/account/wallet-balance
  - WS: public ticker/orderbook, private execution（将来）
- FGRD
  - 監視: 既知の WS（swap*List_BTC）
  - 発注: 仕様確定次第実装

## ファイル構成
- /Bot/config.yaml
- /Bot/main.py
- /Bot/core/engine.py, signals.py, portfolio.py
- /Bot/exchanges/bybit.py, fgrd.py
- /Bot/storage/kv.py, journal.py
- /Bot/utils/timebar.py, backoff.py

## 受入基準（MVP）
- ドライランで Entry/Exit 判定が仕様通り発火、イベント記録が残る
- パラメータ変更が挙動に反映される
- エラー時に安全に停止/再開できる

## レバレッジ/最大ポジション（追加）
- デフォルトの想定はレバレッジ 10x で運用
- `max_pos_btc` はファンドサイズに応じて可変。評価損益・証拠金状況と維持証拠金率を考慮して自動クリップ

## 段階導入計画
1) ドライラン（24–48h）でシグナル妥当性と頻度を検証
2) Bybit片側の最小ロット実発注（ヘッジ片側手動）
3) FGRD API確定後、両側同時実発注に拡張
