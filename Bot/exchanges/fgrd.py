from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional
import time
import hmac
import hashlib
import httpx
import subprocess
import json


@dataclass
class FGRDConfig:
    base_url: str
    api_key: str
    api_secret: str
    bearer_token: str = ""
    cookie: str = ""


class FGRDClient:
    def __init__(self, cfg: FGRDConfig) -> None:
        self.cfg = cfg
        # 一部APIはHTTP/2依存の挙動のため http2=True を有効化
        self.client = httpx.Client(timeout=10.0, http2=True)

    # NOTE: 署名形式は未確定。観測後に実装を差し替える。
    def _sign(self, method: str, path: str, body: str, ts: str) -> str:
        payload = (method.upper() + path + body + ts).encode()
        return hmac.new(self.cfg.api_secret.encode(), payload, hashlib.sha256).hexdigest()

    def _headers(self, method: str, path: str, body: str = "") -> Dict[str, str]:
        # 優先度: Bearer -> Cookie -> HMAC 署名
        headers: Dict[str, str] = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ja;q=0.5",
            "accept-encoding": "gzip, deflate, br, zstd",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "lang": "en",
            "x-requested-with": "XMLHttpRequest",
            "Origin": "https://btcfgrd.com",
            "Referer": "https://btcfgrd.com/",
            "sec-ch-ua": '"Chromium";v="124", "Brave";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
            "sec-gpc": "1",
            "priority": "u=1, i",
        }
        if self.cfg.bearer_token:
            tok = self.cfg.bearer_token.strip()
            # APIは小文字の 'bearer ' を使用しているため合わせる
            if tok.lower().startswith("bearer "):
                headers["authorization"] = tok
            else:
                headers["authorization"] = f"bearer {tok}"
        if self.cfg.cookie:
            headers["cookie"] = self.cfg.cookie
        if method.upper() == "POST":
            # 空ボディPOSTは content-length:0 のみ（content-typeは付与しない）
            if body == "":
                headers["content-length"] = "0"
            else:
                headers["content-type"] = "application/json"
        ts = str(int(time.time() * 1000))
        sig = self._sign(method, path, body, ts)
        headers.update({
            "api-key": self.cfg.api_key,
            "api-sign": sig,
            "api-ts": ts,
        })
        return headers

    def get_balances(self) -> Dict[str, Any]:
        # GET https://api.fgrcbit.com/api/wallet/accounts
        path = "/api/wallet/accounts"
        return self._curl_get_json(path)

    def get_positions(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        # POST https://api.fgrcbit.com/api/user/personalAssets （資産サマリ/ポジション系）
        path = "/api/user/personalAssets"
        return self._curl_post_json(path)

    def get_fund_account(self) -> Dict[str, Any]:
        # POST https://api.fgrcbit.com/api/user/fundAccount
        path = "/api/user/fundAccount"
        return self._curl_post_json(path)

    def _curl_post_json(self, path: str) -> Dict[str, Any]:
        url = self.cfg.base_url + path
        auth = self.cfg.bearer_token.strip()
        if not auth.lower().startswith("bearer "):
            auth = f"bearer {auth}"
        cmd = [
            "curl", url,
            "-s",
            "-X", "POST",
            "-H", "accept: application/json, text/plain, */*",
            "-H", "accept-language: ja;q=0.5",
            "-H", f"authorization: {auth}",
            "-H", "content-length: 0",
            "-H", "lang: en",
            "-H", "origin: https://btcfgrd.com",
            "-H", "priority: u=1, i",
            "-H", "referer: https://btcfgrd.com/",
            "-H", 'sec-ch-ua: "Chromium";v="124", "Brave";v="124", "Not-A.Brand";v="99"',
            "-H", "sec-ch-ua-mobile: ?0",
            "-H", 'sec-ch-ua-platform: "macOS"',
            "-H", "sec-fetch-dest: empty",
            "-H", "sec-fetch-mode: cors",
            "-H", "sec-fetch-site: cross-site",
            "-H", "sec-gpc: 1",
            "-H", "user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "-H", "x-requested-with: XMLHttpRequest",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"curl failed: {result.returncode}: {result.stderr}")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"invalid json: {result.stdout[:200]}")

    def _curl_get_json(self, path: str) -> Dict[str, Any]:
        url = self.cfg.base_url + path
        auth = self.cfg.bearer_token.strip()
        if not auth.lower().startswith("bearer "):
            auth = f"bearer {auth}"
        cmd = [
            "curl", url,
            "-s",
            "-H", "accept: application/json, text/plain, */*",
            "-H", "accept-language: ja;q=0.5",
            "-H", f"authorization: {auth}",
            "-H", "lang: en",
            "-H", "origin: https://btcfgrd.com",
            "-H", "priority: u=1, i",
            "-H", "referer: https://btcfgrd.com/",
            "-H", 'sec-ch-ua: "Chromium";v="124", "Brave";v="124", "Not-A.Brand";v="99"',
            "-H", "sec-ch-ua-mobile: ?0",
            "-H", 'sec-ch-ua-platform: "macOS"',
            "-H", "sec-fetch-dest: empty",
            "-H", "sec-fetch-mode: cors",
            "-H", "sec-fetch-site: cross-site",
            "-H", "sec-gpc: 1",
            "-H", "user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "-H", "x-requested-with: XMLHttpRequest",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"curl failed: {result.returncode}: {result.stderr}")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"invalid json: {result.stdout[:200]}")

    # --- Entrust list (open orders) ---
    def get_current_entrust(self, page: int = 1) -> Dict[str, Any]:
        return self._curl_get_json(f"/api/contract/getCurrentEntrust?page={page}")

    # --- Orders ---
    def create_limit_order(self, symbol: str, side: int, price: str | float, amount: int | float,
                           lever_rate: int | str = 25, order_type: int = 1) -> Dict[str, Any]:
        """Create a limit order on contract market via REST.

        side: 1=買い(ロング), 2=売り(ショート) （ユーザー提供情報）
        order_type: 1=Limit（暫定。変更があれば差し替え）
        amount: 契約数量（ユーザー提供情報で 1=1BTC 分）
        """
        path = "/api/contract/openPosition"
        url = self.cfg.base_url + path
        auth = self.cfg.bearer_token.strip()
        if not auth.lower().startswith("bearer "):
            auth = f"bearer {auth}"
        payload = {
            "side": int(side),
            "symbol": symbol,
            "type": int(order_type),
            "entrust_price": str(price),
            "amount": amount,
            "lever_rate": str(lever_rate),
        }
        cmd = [
            "curl", url, "-s", "-X", "POST",
            "-H", "accept: application/json, text/plain, */*",
            "-H", "accept-language: ja;q=0.5",
            "-H", f"authorization: {auth}",
            "-H", "content-type: application/json;charset=UTF-8",
            "-H", "lang: en",
            "-H", "origin: https://btcfgrd.com",
            "-H", "priority: u=1, i",
            "-H", "referer: https://btcfgrd.com/",
            "-H", 'sec-ch-ua: "Chromium";v="124", "Brave";v="124", "Not-A.Brand";v="99"',
            "-H", "sec-ch-ua-mobile: ?0",
            "-H", 'sec-ch-ua-platform: "macOS"',
            "-H", "sec-fetch-dest: empty",
            "-H", "sec-fetch-mode: cors",
            "-H", "sec-fetch-site: cross-site",
            "-H", "sec-gpc: 1",
            "-H", "user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "-H", "x-requested-with: XMLHttpRequest",
            "--data-raw", json.dumps(payload)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"curl failed: {result.returncode}: {result.stderr}")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"invalid json: {result.stdout[:200]}")

    def cancel_order(self, *, entrust_id: int | str | None = None, order_no: str | None = None, id: str | None = None,
                     client_order_id: str | None = None, symbol: str | None = None) -> Dict[str, Any]:
        """Cancel order via POST /api/contract/cancelEntrust.
        未確定なキー名に対応するため、order_no / id / client_order_id のいずれかを受け取り、存在するキーで送る。
        """
        path = "/api/contract/cancelEntrust"
        url = self.cfg.base_url + path
        auth = self.cfg.bearer_token.strip()
        if not auth.lower().startswith("bearer "):
            auth = f"bearer {auth}"
        body: Dict[str, Any] = {}
        if entrust_id is not None:
            body["entrust_id"] = int(entrust_id)
        if order_no:
            body["order_no"] = order_no
        if id:
            body["id"] = id
        if client_order_id:
            body["clientOrderId"] = client_order_id
        if symbol:
            body["symbol"] = symbol
        cmd = [
            "curl", url, "-s", "-X", "POST",
            "-H", "accept: application/json, text/plain, */*",
            "-H", "accept-language: ja;q=0.5",
            "-H", f"authorization: {auth}",
            "-H", "content-type: application/json;charset=UTF-8",
            "-H", "lang: en",
            "-H", "origin: https://btcfgrd.com",
            "-H", "priority: u=1, i",
            "-H", "referer: https://btcfgrd.com/",
            "-H", 'sec-ch-ua: "Chromium";v="124", "Brave";v="124", "Not-A.Brand";v="99"',
            "-H", "sec-ch-ua-mobile: ?0",
            "-H", 'sec-ch-ua-platform: "macOS"',
            "-H", "sec-fetch-dest: empty",
            "-H", "sec-fetch-mode: cors",
            "-H", "sec-fetch-site: cross-site",
            "-H", "sec-gpc: 1",
            "-H", "user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "-H", "x-requested-with: XMLHttpRequest",
            "--data-raw", json.dumps(body or {"noop": True})
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"curl failed: {result.returncode}: {result.stderr}")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"invalid json: {result.stdout[:200]}")
