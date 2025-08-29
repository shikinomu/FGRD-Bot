# FGRD × Bybit アービトラージ戦略 検証メニュー（データ: compare_10s.csv）

## 対象データ
- 入力: `compare_10s.csv`
  - 列: timestamp, spot_fgrd_bid/ask/last, spot_bybit_bid/ask/last, swap_fgrd_bid/ask/last, swap_bybit_bid/ask/last
  - 粒度: 10秒

## 想定戦略（サマリ）
- 現物クロス所要差（Spot Arbitrage）
  - 条件: spot_fgrd_bid − spot_bybit_ask > コスト合計 ⇒ Bybitで買い → FGRDで売り
  - 逆方向: spot_bybit_bid − spot_fgrd_ask > コスト合計 ⇒ FGRDで買い → Bybitで売り
- 先物-現物ベーシス（Cash-and-Carry/Reverse）
  - 条件: swap側とspot側の乖離（同取引所・クロス取引所）
  - 例: FGRDのswap_fgrdとspot_fgrd、Bybitのswap_bybitとspot_bybit、FGRDとBybit跨ぎ
- クロス取引所スプレッド（Swap Arbitrage）
  - 条件: swap_fgrd_bid − swap_bybit_ask > コスト合計、または逆方向
- 三角/擬似三角（本データではUSDT建のみのため簡略）

## コストモデル（最小要件）
- 取引手数料（taker）: exchange別・現物/契約別で係数設定
- スリッページ: 1ティック or 比例（例: 1–3 bps）
- 資金調達/資金利用コスト: funding（契約）、金利（スポット調達）
- 出金/入金/送金コスト（必要に応じて）

## リスク項目
- 約定不一致（10秒粒度のため同時刻ズレ）
- 約定量制約（本データはトップレベルのみ）
- 価格乖離の持続性（Mean-reversionか、トレンドか）
- FGRDサイドの実行可否・ロット/制限
- BybitサイドAPI制限/レイテンシ

## メトリクス定義
- スプレッド
  - spot_spread_fgrd_bybit = spot_fgrd_bid − spot_bybit_ask（往路）
  - spot_spread_bybit_fgrd = spot_bybit_bid − spot_fgrd_ask（復路）
  - swap_spread_fgrd_bybit = swap_fgrd_bid − swap_bybit_ask（往路）
  - swap_spread_bybit_fgrd = swap_bybit_bid − swap_fgrd_ask（復路）
- ベーシス（同一所内）
  - basis_fgrd = swap_fgrd_last − spot_fgrd_last
  - basis_bybit = swap_bybit_last − spot_bybit_last
- 有効スプレッド（コスト控除後）
  - eff_spread = raw_spread − 手数料 − スリッページ − ファンディング影響
- 勝率、平均利幅、MaxDD、シャープ類似（単純化）

## 分析メニュー（実行順）
1) 前処理
   - 欠損の前方/後方補完
   - lastが欠落時は中値で補完（実装済みに依存）
   - タイムゾーン確認（UTCのまま）
2) スプレッド計算と閾値ヒット
   - 4種のクロススプレッドを時系列で算出
   - コストモデルを引いてeff_spreadを評価
   - 閾値（例: 0, 1, 2, 3 USD）でヒット率・平均利幅
3) 滞在時間分析（持続性）
   - eff_spread > 0 が連続する区間長分布
   - 同区間のボラティリティ
4) ベーシス分析
   - basis_fgrd, basis_bybit の分布/相関
   - basis乖離が大きい局面とスプレッドの関係
5) ルールバックテスト（疑似）
   - エントリー: eff_spread > 0 の立上がり
   - エグジット: eff_spread <= 0、または最大保持時間（例: 60–300秒）
   - PnL算出（手数料/スリッページ控除）
6) 感度分析
   - 手数料係数（±50%）
   - スリッページ（1–5bps）
   - 閾値（0–5 USD）
7) 実行可能性チェック
   - 同時約定想定誤差（±1サイクル）
   - 取引数量の想定（固定ロット vs 可変）

## 戦略案（具体化）
- Strategy A: Cross-Spot Quick Flip
  - 条件: spot_fgrd_bid − spot_bybit_ask > fee_sum + slip
  - 執行: Bybit買い + FGRD売り、目標: 1–2分以内にクローズ（逆方向成立で即時）
- Strategy B: Cross-Swap Quick Flip
  - 条件: swap_fgrd_bid − swap_bybit_ask > fee_sum + slip
  - 執行: Bybit(USDT無期限)買い + FGRD(契約)売り
- Strategy C: Basis Revert（同一取引所）
  - 条件: basis_fgrd > thresh でFGRDの現物買い+契約売り（または逆）
  - エグジット: basisの均衡/反転、または時間カット
- Strategy D: Cross-Basis Revert（取引所跨ぎ）
  - 条件: basis_fgrd − basis_bybit が閾値超え

## 最低限の可視化
- スプレッド4種の時系列ライン
- eff_spreadのヒット区間ハイライト
- basis_fgrd / basis_bybit の時系列・ヒスト

## 次ステップ
- 上記メニューに沿ったノートブック/スクリプト雛形を `/trading_strategy/notebooks/` に作成
- 手数料/スリッページの仮値を `config.yaml` で集中管理
- 成果物: ヒット率・平均利幅・バックテストPnLのサマリ表

