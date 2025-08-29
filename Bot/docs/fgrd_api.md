## FGRD 発注/残高取得の実装方針（市場成行・ポジション・資産）

### 目的
- Bot から FGRD で市場成行注文を出し、約定/ポジション/資産を取得するための実装手順を明文化する。

### 手法サマリ
- 公式API仕様が未公開の前提で、まずは「アプリ通信の観測→エンドポイント特定→実装」
- 代替として「UI自動化（Appium/XCUITest）」をバックアップ手段に用意

---

### 1) 通信観測（MITM）で API を特定
- 推奨ツール: Proxyman / Charles Proxy / mitmproxy（いずれも可）
- 対象端末: iPhone 実機 or iOS Simulator（Simulator は証明書ピン留めが無効な場合が多く、成功率が高い）

手順（例: Proxyman）
1. Mac で Proxyman を起動し、証明書をインストール
   - Proxyman > Certificate > Install on macOS
   - iPhone へも配布（Install on iOS）→ iPhone 側 設定 > 一般 > 情報 > 証明書信頼設定 でフル信頼にする
2. iPhone の Wi‑Fi 設定で HTTP Proxy を「手動」→ Mac の IP とポート（デフォルト 9090 等）を指定
3. FGRD アプリを起動し、以下の操作を実施
   - 小額で「市場成行」注文を送る（約定確認まで）
   - 注文履歴/ポジション/資産画面を開く
4. Proxyman で HTTPS/WS の通信を確認し、以下を記録
   - Base URL（例: `https://api.fgrcbit.com` 等）
   - エンドポイント: 注文作成（market）、注文一覧/詳細、ポジション一覧、口座残高、WS の private チャンネル
   - 認証方式: ヘッダキー（例: apiKey）、署名方式（HMAC?）、タイムスタンプ、nonce、パラメータ順序
   - WebSocket: 認証メッセージ、サブスクライブトピック、ping/pong

補足（証明書ピン留めで見えない場合）
- iOS Simulator で再試行（成功率高）
- Frida/objection 等で SSL ピン留め無効化（自己責任）
- 最低限、Xcode > Developer Tools > Instruments > Network でも宛先ホストとパスは把握可能

---

### 2) 取得すべき主要API（想定）
- REST（推定）
  - POST `/order/create`（market）: シンボル、売買、数量、timestamp、signature
  - GET `/order/active` / `/order/history`
  - GET `/position/list`
  - GET `/account/balance`
- WebSocket（推定）
  - private 認証 → `order`, `execution`, `position`, `wallet` などのトピック購読
  - ping/pong プロトコル

観測時のメモ事項
- 署名アルゴリズム（例: `HMAC_SHA256(secret, method+path+query+body+ts)`）
- タイムスタンプ単位（ms/s）・時差許容
- 数量/価格の最小単位、精度、最小発注額

---

### 3) Bot 実装へのマッピング
- `Bot/exchanges/fgrd.py`（想定インターフェース）
  - `create_market_order(symbol, side, size_btc, client_id)`
  - `get_positions(symbol)` / `get_open_orders(symbol)`
  - `get_balances()`
  - `connect_private_ws(on_event)`（order/execution/position/wallet を受信）
- `strategy_rules.json` に従い、成行サイズは「両所の最良数量の小さい方」「max_pos」「レバ制約」でクリップ

---

### 4) UI 自動化のバックアップ（API 判明までの暫定）
- Appium + WebDriverAgent（iOS）で FGRD の「成行」UI を自動操作
- XCUITest（Xcode）でテストコード化
- iOS ショートカット/URL Scheme があれば呼び出し（要調査）
- 約定/ポジション画面の OCR は最終手段（精度/保守性低）

---

### 5) セキュリティ/運用上の注意
- 個人 API キー/トークンは決してログ/リポジトリに残さない
- 少額/テストモードで検証、レート制限/クールダウンを実装
- 時刻同期（NTP）と署名時刻のドリフト対策

---

### 6) 次のアクション
- 上記手順で実際に小額の「市場成行」を1件送信→ HAR/Proxyman セッションを保存
- 当該ログ（署名部は伏せても可）を共有ください。すぐに `exchanges/fgrd.py` の実装に着手します。

参考: リポジトリ `FGRD-Bot` に実装を継続反映します（`main` ブランチ）。
