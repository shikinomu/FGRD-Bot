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

---

### 7) 実装ノウハウ（確定事項）
- 認証は JWT を `authorization: bearer <JWT>` で送る（先頭は小文字の bearer）。
- 共通ヘッダ（成功確認済み）
  - `accept: application/json, text/plain, */*`
  - `accept-language: ja;q=0.5`
  - `authorization: bearer <JWT>`
  - `lang: en`
  - `origin: https://btcfgrd.com`, `referer: https://btcfgrd.com/`
  - `user-agent: Chrome系`, `x-requested-with: XMLHttpRequest`
  - `sec-*` 系ヘッダはそのまま送れば可
- POST空ボディでは `content-length: 0` を付与（`content-type` は不要）。
- HTTP/2対応のクライアントでも動作するが、実運用では cURL互換ヘッダでの送信が最も安定。

主要エンドポイント（資産系）
- GET `/api/wallet/accounts`（口座一覧）
- POST `/api/user/personalAssets`（資産サマリ）
- POST `/api/user/fundAccount`（資金口座）

cURL例
```bash
curl -s 'https://api.fgrcbit.com/api/user/personalAssets' -X POST \
  -H 'accept: application/json, text/plain, */*' -H 'accept-language: ja;q=0.5' \
  -H 'authorization: bearer <JWT>' -H 'content-length: 0' -H 'lang: en' \
  -H 'origin: https://btcfgrd.com' -H 'referer: https://btcfgrd.com/' \
  -H 'user-agent: Mozilla/5.0' -H 'x-requested-with: XMLHttpRequest'

curl -s 'https://api.fgrcbit.com/api/user/fundAccount' -X POST \
  -H 'accept: application/json, text/plain, */*' -H 'accept-language: ja;q=0.5' \
  -H 'authorization: bearer <JWT>' -H 'content-length: 0' -H 'lang: en' \
  -H 'origin: https://btcfgrd.com' -H 'referer: https://btcfgrd.com/' \
  -H 'user-agent: Mozilla/5.0' -H 'x-requested-with: XMLHttpRequest'

curl -s 'https://api.fgrcbit.com/api/wallet/accounts' \
  -H 'accept: application/json, text/plain, */*' -H 'accept-language: ja;q=0.5' \
  -H 'authorization: bearer <JWT>' -H 'lang: en' \
  -H 'origin: https://btcfgrd.com' -H 'referer: https://btcfgrd.com/'
```

トークンの取得（Web UI）
- DevTools → Network → 対象リクエスト（例: `/api/wallet/accounts`）→ Headers → `Authorization` をコピー
- あるいは `localStorage.getItem('token')`（実装により鍵名は異なる）

---

### 8) Bot配線（現状）
- `Bot/core/engine.py` にて 60秒ごとに以下を取得し `Bot/account_snapshot.csv` に追記
  - GET `/api/wallet/accounts`
  - POST `/api/user/fundAccount`
- 送信は cURL フォールバック（subprocess）で cURL と同一ヘッダを送信
- `personalAssets` は同ルートで拡張可能

---

### 9) トラブルシュート
- `Not logged in` の場合:
  - Authorization が空／`bearer` が無い／トークン失効の可能性
  - POST空ボディは `content-length: 0` 必須
- Cookie は現状不要（Network に `cookie:` 無し）。`config.yaml` に項目は用意済み。

---

### 10) セキュリティ
- `bearer_token` はローカル `Bot/config.yaml` のみに保存。Gitへコミットしないこと。
- トークンの定期更新とローテーションを推奨。

---

### 11) 契約（先物）発注/取消・未約定一覧（確定）

#### 共通
- Base: `https://api.fgrcbit.com`
- 認証: `authorization: bearer <JWT>`（小文字 `bearer`）
- ヘッダ例（成功実績あり）
  - `accept: application/json, text/plain, */*`
  - `accept-language: ja;q=0.5`
  - `lang: en`
  - `origin: https://btcfgrd.com`, `referer: https://btcfgrd.com/`
  - `user-agent: Chrome系`, `x-requested-with: XMLHttpRequest`
  - `sec-*` 一式

#### 11.1 発注（Limit）
- POST `/api/contract/openPosition`
- Payload（JSON）
  - `side`（int）: 1=買い/ロング（ユーザー確認済み）
  - `symbol`（str）: 例 `"BTC"`
  - `type`（int）: 1=Limit（暫定。今後の差分は実測で更新）
  - `entrust_price`（str|number）: 例 `"105000"`
  - `amount`（number）: 契約数量。ユーザー確認で「1=1BTC分」
  - `lever_rate`（str|int）: 例 `25`

curl 例（実績）
```bash
curl 'https://api.fgrcbit.com/api/contract/openPosition' \
  -H 'accept: application/json, text/plain, */*' \
  -H 'accept-language: ja;q=0.5' \
  -H 'authorization: bearer <JWT>' \
  -H 'content-type: application/json;charset=UTF-8' \
  -H 'lang: en' -H 'origin: https://btcfgrd.com' -H 'referer: https://btcfgrd.com/' \
  --data-raw '{"side":1,"symbol":"BTC","type":1,"entrust_price":"105000","amount":1,"lever_rate":"25"}'
```

売り（ショート）例（side=2）
```bash
curl 'https://api.fgrcbit.com/api/contract/openPosition' \
  -H 'accept: application/json, text/plain, */*' \
  -H 'accept-language: ja;q=0.5' \
  -H 'authorization: bearer <JWT>' \
  -H 'content-type: application/json;charset=UTF-8' \
  -H 'lang: en' -H 'origin: https://btcfgrd.com' -H 'referer: https://btcfgrd.com/' \
  --data-raw '{"side":2,"symbol":"BTC","type":1,"entrust_price":"120009","amount":1,"lever_rate":"25"}'
```

レスポンス例
```json
{"code":200,"message":"Entrust the success","data":null}
```
注意: `data` が `null` のため、発注直後の `entrust_id` は未約定一覧から取得する。

#### 11.2 未約定一覧（open orders）
- GET `/api/contract/getCurrentEntrust?page=1`
- レスポンス例（抜粋）
```json
{
  "code":200,
  "data":{
    "data":[{
      "id":180778,
      "order_no":"PCB175...",
      "order_type":1,
      "side":1,
      "symbol":"BTC",
      "type":1,
      "entrust_price":110656,
      "amount":1,
      "lever_rate":25,
      "status":1,
      "hang_status":1
    }]}
}
```
- `entrust_id` は `id` または `entrust_id` として返る。直近の注文は `symbol/side/entrust_price/status=1` で特定。

#### 11.3 取消（Cancel）
- POST `/api/contract/cancelEntrust`
- Payload（JSON）
  - `symbol`（str）: 例 `"BTC"`
  - `entrust_id`（int）: 未約定一覧の `id`（または `entrust_id`）

curl 例（実績）
```bash
curl 'https://api.fgrcbit.com/api/contract/cancelEntrust' \
  -H 'accept: application/json, text/plain, */*' \
  -H 'accept-language: ja;q=0.5' \
  -H 'authorization: bearer <JWT>' \
  -H 'content-type: application/json;charset=UTF-8' \
  -H 'lang: en' -H 'origin: https://btcfgrd.com' -H 'referer: https://btcfgrd.com/' \
  --data-raw '{"symbol":"BTC","entrust_id":180779}'
```
レスポンス例: `{ "code":200, "message":"success", "data":null }`

#### 11.4 上限取得（参考）
- GET `/api/contract/openNum?symbol=BTC&lever_rate=25`（建玉可能数量等を返す）

#### 11.5 Bot 実装（対応状況）
- `exchanges/fgrd.py`
  - `create_limit_order(symbol, side, price, amount, lever_rate=25, order_type=1)`
  - `get_current_entrust(page=1)`
  - `cancel_order(entrust_id=..., symbol=...)`
  - 送信は cURL 互換ヘッダで安定運用（subprocess フォールバック）
- `order_smoke.py`（スモーク）
  - 105000 で 1BTC 買い指値 → `getCurrentEntrust` で `entrust_id` 取得 → 20秒後に `cancelEntrust`
  - 実績: `entrust_id=180782` を抽出し、`code=200 success` で取消確認済み

#### 11.6 パラメータ備考
- side: 1=買い/ロング（ユーザー確認済み）
- type: 1=Limit（暫定。将来の変更に備えて実測で随時更新）
- amount: 1=1BTC 分（ユーザー確認済み）。単位定義に変更が入った場合は再確認

