## 目的
- **本番常駐**: FGRD/Bybit 価格監視、スプレッド計算、発注（将来）、資産スナップショット。
- **軽量運用**: t2.microでも可。推奨は t3.micro/t4g.micro。

## 対象AWSコンポーネント
- **EC2**: Amazon Linux 2023 または Ubuntu 22.04 LTS
- **IAMロール**: SSM Parameter Store/Secrets Manager 読取、CloudWatch Logs 送信（任意）
- **SSM Parameter Store or Secrets Manager**: 機密情報管理（JWT/Bearer, Cookie, 将来のBybit鍵）
- **CloudWatch Logs**(任意): ログ集約/アラート

## インスタンスタイプ指針
- 最小: t2.micro (1 vCPU / 1GB) … Bot本体のみ（バックテストは手元/バッチ）
- 推奨: t3.micro or t4g.micro … CPUクレジット安定

## ネットワーク/セキュリティ
- **Security Group**
  - Outbound: HTTPS(443)のみ許可
  - Inbound: SSH(22)のみ。接続元IPを制限
- **OSハードニング**: 自動アップデート、UFW/iptables(必要時)

## IAMポリシー最小権限
- ssm:GetParameter, ssm:GetParameters, kms:Decrypt（対象パラメータ鍵に限定）
- secretsmanager:GetSecretValue（使用時のみ、対象シークレットに限定）
- logs:CreateLogStream, logs:PutLogEvents（CloudWatchに送る場合）

## 機密情報と設定
- 機密はGitへコミット禁止。以下をSSM/Secretsで保持。
  - `FGRD_BEARER`（JWT）
  - `FGRD_COOKIE`（必要に応じて）
  - 将来: Bybit API Key/Secret（`BYBIT_KEY`, `BYBIT_SECRET`）
- `Bot/config.yaml` は非機密（手数料/スリッページ/パラメータ等）。機密は環境変数で注入。
- `Bot/exchanges/fgrd.py` は Bearer → Cookie → HMAC の順で認証を試行（現状はBearer/Cookie運用）。

## 依存関係
- Python 3.10+
- `Bot/requirements.txt`: httpx[http2], websockets, pydantic, tenacity, orjson, PyYAML
- `curl`（cURLフォールバック用）
- awscli（起動時にSSM/Secretsから注入する場合）

## セットアップ手順（例: Ubuntu 22.04）
```bash
sudo apt update && sudo apt install -y python3-venv python3-pip curl unzip
# awscli
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip && unzip awscliv2.zip && sudo ./aws/install
# リポジトリ取得
sudo mkdir -p /opt/fgrd && sudo chown "$USER" /opt/fgrd
cd /opt/fgrd
git clone https://github.com/shikinomu/FGRD-Bot .
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip && pip install -r Bot/requirements.txt
```

## 機密の注入（SSM Parameter Store使用例）
- 事前: `FGRD_BEARER` を SecureString で `/${env}/fgrd/bearer` に保存
```bash
aws ssm put-parameter --name "/prod/fgrd/bearer" --type SecureString --value "<JWT>" --overwrite
```
- 起動時に環境変数へ注入（systemdのExecStartPreなどで）
```bash
export FGRD_BEARER=$(aws ssm get-parameter --name "/prod/fgrd/bearer" --with-decryption --query Parameter.Value --output text)
# （必要に応じて）
export FGRD_COOKIE=$(aws ssm get-parameter --name "/prod/fgrd/cookie" --with-decryption --query Parameter.Value --output text 2>/dev/null || true)
```

## 実行方式
- 常駐は systemd で実装。
- 本番: 価格取得/スプレッド検知/資産スナップショットに限定。バックテストは手元/バッチ。

### systemd ユニット例
`/etc/systemd/system/fgrd-bot.service`
```ini
[Unit]
Description=FGRD Bot Engine
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/fgrd
Environment="PYTHONUNBUFFERED=1"
# 起動前にSSMから注入
ExecStartPre=/bin/bash -c 'export AWS_REGION=ap-northeast-1; \
  export FGRD_BEARER=$(aws ssm get-parameter --name "/prod/fgrd/bearer" --with-decryption --query Parameter.Value --output text); \
  export FGRD_COOKIE=$(aws ssm get-parameter --name "/prod/fgrd/cookie" --with-decryption --query Parameter.Value --output text 2>/dev/null || true); \
  echo "Env injected"'
# Bot起動（config.yamlはリポジトリ内、機密は環境変数経由で参照）
ExecStart=/opt/fgrd/.venv/bin/python /opt/fgrd/Bot/main.py
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full

[Install]
WantedBy=multi-user.target
```

## ログ/監視
- `journalctl -u fgrd-bot -f` で追跡
- CloudWatch 送信（任意）: CloudWatch Agent か `awslogs` を使用
- 健全性チェック: 60秒毎の `/api/wallet/accounts` 呼び出しに失敗したら警告ログ

## 運用ルール
- **トークン更新**: 401/"Not logged in" を検知→SSMの`/${env}/fgrd/bearer`を更新→`systemctl restart fgrd-bot`
- **変更管理**: `git pull && systemctl restart`
- **ログ衛生**: Bearer/Cookieはログ出力しない（実装済）

## フォールバック/冗長化
- `FGRDClient` は cURLフォールバックで安定化済
- 単一AZ障害に対しては再起動で復旧。必要ならASG + ヘルスチェックで再作成

## 性能/コスト注意
- t2.micro では画像生成等の重処理は避ける
- 常駐: < 100MB RAM 目安（環境により増減）

## 手動デプロイ手順（要約）
1) EC2起動 + SG/IAMロール適用
2) リポジトリ取得 + venv + 依存導入
3) SSMにBearer等を登録
4) systemd ユニット設置→ `systemctl enable --now fgrd-bot`

## 既知の注意事項
- JWTトークンはWeb UIと同一のもの。期限切れや再ログインで更新が必要
- `curl` バージョン差異で稀に挙動差が出る場合あり（標準のcurlで問題無し）
- HTTP/2の挙動差により`httpx`単体で認証不可となるケースがあるため、cURLフォールバックを維持

## 将来拡張
- Bybit API鍵の安全保管（SSM/Secrets）と実売買実装
- CloudWatchメトリクス（ポジション・残高・PnL）可視化
- ローテーション済みトークンの自動反映（SSM変更トリガ）
