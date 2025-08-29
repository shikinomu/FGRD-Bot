## 目的
- Bybit 現物/USDT無期限のクライアント実装方針と実装要件を定義
- Botのスプレッド裁定戦略に必要な最小セットから段階的に拡張

## 対象とするAPI/機能
- 認証: API Key/Secret (HMAC SHA256) + recvWindow/nonce
- マーケットデータ: 参照専用（既存compare_10s.csvは継続）。将来はWS: orderbook.1, tickers
- 注文: 市場/指値、新規/キャンセル
- 口座: 残高、ポジション、未約定一覧、取引履歴（後方検証/コスト検証用）

## ストラテジ連携（最小）
- エントリ: at market（最良気配の小さい方にクリップ）
- サイズ: 
  - BTC: `min(best_bid_qty, best_ask_qty, max_pos_btc)`
  - レバレッジ: 10x（USDT建て）
- 逆張りロジック（外部JSON）: `reverse_entry`(>=800, 3連続) → `reverse_exit`(<=400, 3連続)
- ミーンリバージョン: `entry`(abs<=75, 2連続) → `exit.take_profit`(>=300, 3連続) or `exit.stop_loss`(<=-200, 3連続)

## 設計
- パッケージ: `Bot/exchanges/bybit.py`
- 依存: `httpx`（REST）, 将来 `websockets`（WS）
- 認証ヘッダ生成: `X-BAPI-API-KEY`, `X-BAPI-TIMESTAMP`, `X-BAPI-SIGN`, `X-BAPI-RECV-WINDOW`
- エンドポイント（v5）例:
  - `GET /v5/account/wallet-balance` （残高）
  - `GET /v5/position/list` （ポジション）
  - `GET /v5/order/realtime` （未約定）
  - `POST /v5/order/create` （新規）
  - `POST /v5/order/cancel` （キャンセル）
- リクエスト署名: prehash = timestamp + api_key + recvWindow + (query/body)、HMAC-SHA256 → hex。Content-Type: application/json

## 実装要件（MVP）
1) クライアントクラス `BybitClient`
   - 構成: base_url, api_key, api_secret, recv_window=5000
   - メソッド:
     - `get_wallet_balance(coin='USDT')`
     - `get_positions(symbol='BTCUSDT')`
     - `get_open_orders(symbol='BTCUSDT')`
     - `create_order(symbol, side, order_type, qty, price=None, time_in_force='IOC', reduce_only=False)`
     - `cancel_order(symbol, order_id)`
   - リトライ/タイムアウト: `tenacity`/httpx timeout、429/5xxで指数バックオフ
2) 実行ラッパ `Executor`
   - 役割: signals→サイズ決定→Bybit発注/キャンセル、失敗時再試行
   - 片側のみ実行（FGRD側の建玉と整合）
3) 例外/フェイルセーフ
   - 残高/ポジション検証→不足時は発注スキップ
   - 連続エラーでクールダウン
   - 価格逸脱チェック（ミッドからの乖離）

## データモデル
- 設定: `Bot/config.yaml` に `exchanges.bybit` セクション追加（key/secret/recvWindow）
- ルール: `Bot/strategy_rules.json` を共有
- ログ: `Bot/trade_journal.csv` へbybit側イベントも追記（engine側で区別タグ）

## 疎通/スモーク
- `Bot/bybit_smoke.py` を作成し、`get_wallet_balance`→`create_order(limit IOC tiny qty)`→`get_open_orders`→`cancel_order` を連続実行
- 実行はdry-run可（REST呼び出し部のみスキップ）

## セキュリティ
- キーはGitに含めない。AWS SSM/Secretsから環境変数注入
- ログに署名・鍵を出力しない

## 将来拡張
- WSでベスト気配/出来高取得、板厚からサイズ決定の精緻化
- 部分約定検出と追撃（TWAP）
- FGRD/Bybit間のレイテンシと滑りの統計計測
