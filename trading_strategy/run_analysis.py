import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

BASE = Path(__file__).resolve().parent
CSV = BASE.parent / 'compare_10s.csv'
IMG = BASE / 'img'
IMG.mkdir(parents=True, exist_ok=True)

# 可変パラメータ（簡易コストモデル）
TAKER_FEE_SPOT = 0.001  # 0.1%
TAKER_FEE_SWAP = 0.0006 # 0.06%
SLIPPAGE_USD = 0.5      # 0.5 USD 相当
Z_ENTRY = 1.5
Z_EXIT = 0.3
SMA_WINDOW = 36  # 6分（10s粒度×36）
STD_WINDOW = 36
UNIT = 1.0  # 1枚あたりの想定（PnLはUSD）
ONEWAY_Z_ENTRY = 2.0
ONEWAY_Z_EXIT = 0.5
MAX_HOLD_SEC = 600  # 10分


def load():
    df = pd.read_csv(CSV)
    # 欠損を前方/後方補完
    df = df.sort_values('timestamp')
    df.reset_index(drop=True, inplace=True)
    df = df.fillna(method='ffill').fillna(method='bfill')
    return df


def compute_spreads(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    # スプレッド定義
    d['spot_spread_fgrd_bybit'] = d['spot_fgrd_bid'] - d['spot_bybit_ask']
    d['spot_spread_bybit_fgrd'] = d['spot_bybit_bid'] - d['spot_fgrd_ask']
    d['swap_spread_fgrd_bybit'] = d['swap_fgrd_bid'] - d['swap_bybit_ask']
    d['swap_spread_bybit_fgrd'] = d['swap_bybit_bid'] - d['swap_fgrd_ask']
    # ベーシス
    d['basis_fgrd'] = d['swap_fgrd_last'] - d['spot_fgrd_last']
    d['basis_bybit'] = d['swap_bybit_last'] - d['spot_bybit_last']
    return d


def effective_spread(raw: pd.Series, fee_a: float, fee_b: float) -> pd.Series:
    # 片側ずつtaker費用、スリッページをUSDで近似控除
    return raw - (fee_a + fee_b) * 0.5 * raw.abs() - SLIPPAGE_USD


def add_effective(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d['eff_spot_fgrd_bybit'] = effective_spread(d['spot_spread_fgrd_bybit'], TAKER_FEE_SPOT, TAKER_FEE_SPOT)
    d['eff_spot_bybit_fgrd'] = effective_spread(d['spot_spread_bybit_fgrd'], TAKER_FEE_SPOT, TAKER_FEE_SPOT)
    d['eff_swap_fgrd_bybit'] = effective_spread(d['swap_spread_fgrd_bybit'], TAKER_FEE_SWAP, TAKER_FEE_SWAP)
    d['eff_swap_bybit_fgrd'] = effective_spread(d['swap_spread_bybit_fgrd'], TAKER_FEE_SWAP, TAKER_FEE_SWAP)
    return d


def plot_series(df: pd.DataFrame, cols, title, fname):
    plt.figure(figsize=(12,6))
    for c in cols:
        plt.plot(df['timestamp'], df[c], label=c)
    plt.xticks(rotation=90, fontsize=7)
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(IMG / fname, dpi=150)
    plt.close()


def summarize_hits(s: pd.Series, thresh: float) -> dict:
    hits = (s > thresh).sum()
    ratio = hits / len(s)
    avg_gain = s[s > thresh].mean() if hits > 0 else 0.0
    return {'thresh': thresh, 'hits': int(hits), 'ratio': float(ratio), 'avg_gain': float(avg_gain)}


def run():
    df = load()
    df = compute_spreads(df)
    df = add_effective(df)

    # 可視化
    plot_series(df, ['spot_spread_fgrd_bybit','spot_spread_bybit_fgrd'], 'Spot spread (raw)', 'spot_spread_raw.png')
    plot_series(df, ['swap_spread_fgrd_bybit','swap_spread_bybit_fgrd'], 'Swap spread (raw)', 'swap_spread_raw.png')
    plot_series(df, ['eff_spot_fgrd_bybit','eff_spot_bybit_fgrd'], 'Spot spread (effective)', 'spot_spread_eff.png')
    plot_series(df, ['eff_swap_fgrd_bybit','eff_swap_bybit_fgrd'], 'Swap spread (effective)', 'swap_spread_eff.png')
    plot_series(df, ['basis_fgrd','basis_bybit'], 'Basis (swap - spot)', 'basis.png')

    # ヒット集計
    thresholds = [0.0, 0.5, 1.0, 2.0]
    summaries = []
    for t in thresholds:
        summaries.append({'series':'eff_spot_fgrd_bybit', **summarize_hits(df['eff_spot_fgrd_bybit'], t)})
        summaries.append({'series':'eff_spot_bybit_fgrd', **summarize_hits(df['eff_spot_bybit_fgrd'], t)})
        summaries.append({'series':'eff_swap_fgrd_bybit', **summarize_hits(df['eff_swap_fgrd_bybit'], t)})
        summaries.append({'series':'eff_swap_bybit_fgrd', **summarize_hits(df['eff_swap_bybit_fgrd'], t)})
    pd.DataFrame(summaries).to_csv(IMG / 'hit_summary.csv', index=False)

def backtest_swap_pair(df: pd.DataFrame):
    """
    ペアトレード検証（契約のみ）
    位置づけ:
      pos = +1: FGRD買い + Bybit売り（スプレッド s = fgrd - bybit 上昇で利益）
      pos = -1: FGRD売り + Bybit買い（スプレッド低下で利益）
    PnL増分: dPnL = pos * Δs
    取引コスト: 片道で両側taker+スリッページ（USD）を差引。往復時は2倍。
    """
    d = df.copy()
    d['s'] = d['swap_fgrd_last'] - d['swap_bybit_last']
    d['sma'] = d['s'].rolling(SMA_WINDOW, min_periods=5).mean()
    d['std'] = d['s'].rolling(STD_WINDOW, min_periods=5).std(ddof=0)
    d['z'] = (d['s'] - d['sma']) / d['std']
    d['z'] = d['z'].replace([np.inf, -np.inf], np.nan).fillna(0.0)

    pos = 0
    pnl = 0.0  # 累積PnL（ネット）
    equities = []
    poss = []
    trades = []  # list of dicts
    entry_idx = None
    entry_s = None
    entry_pos = None
    entry_cost = 0.0
    equity_at_entry = 0.0

    def trade_cost(row):
        # 片道で両サイドのtaker+スリッページ×2
        price_f = float(row['swap_fgrd_last']) * UNIT
        price_b = float(row['swap_bybit_last']) * UNIT
        fee = TAKER_FEE_SWAP * (abs(price_f) + abs(price_b))
        slip = 2.0 * SLIPPAGE_USD
        return fee + slip

    for i in range(1, len(d)):
        row_prev = d.iloc[i-1]
        row = d.iloc[i]
        ds = float(row['s'] - row_prev['s']) * UNIT

        # マークトゥマーケット
        pnl += pos * ds

        # エントリー/エグジット判定
        z = float(row['z'])
        new_pos = pos

        if pos == 0:
            if z > Z_ENTRY:
                new_pos = -1  # 高位→縮小期待
            elif z < -Z_ENTRY:
                new_pos = +1  # 低位→拡大期待
            if new_pos != 0:
                c = trade_cost(row)
                pnl -= c
                entry_idx = i
                entry_s = float(row['s'])
                entry_pos = new_pos
                entry_cost = c
                equity_at_entry = pnl
        else:
            exit_signal = abs(z) < Z_EXIT  # 中性域で利確/撤退
            reverse_signal = (z > Z_ENTRY and pos == +1) or (z < -Z_ENTRY and pos == -1)
            if reverse_signal:
                # 反転（エグジット+エントリー）
                c = trade_cost(row) * 2.0
                pnl -= c
                # 記録（クローズ分）
                trade_pnl = pnl - equity_at_entry
                trades.append({
                    'entry_idx': entry_idx,
                    'exit_idx': i,
                    'entry_pos': entry_pos,
                    'exit_pos': -pos,
                    'entry_s': entry_s,
                    'exit_s': float(row['s']),
                    'pnl_net': float(trade_pnl),
                    'cost_total': float(entry_cost + c/2.0),
                    'duration_sec': (pd.to_datetime(row['timestamp']) - pd.to_datetime(d['timestamp'].iloc[entry_idx])).total_seconds()
                })
                # 新規エントリー
                entry_idx = i
                entry_s = float(row['s'])
                entry_pos = -pos
                entry_cost = c/2.0
                equity_at_entry = pnl
                new_pos = -pos
            elif exit_signal:
                # クローズ
                c = trade_cost(row)
                pnl -= c
                trade_pnl = pnl - equity_at_entry
                trades.append({
                    'entry_idx': entry_idx,
                    'exit_idx': i,
                    'entry_pos': entry_pos,
                    'exit_pos': 0,
                    'entry_s': entry_s,
                    'exit_s': float(row['s']),
                    'pnl_net': float(trade_pnl),
                    'cost_total': float(entry_cost + c),
                    'duration_sec': (pd.to_datetime(row['timestamp']) - pd.to_datetime(d['timestamp'].iloc[entry_idx])).total_seconds()
                })
                new_pos = 0
                entry_idx = None
                entry_s = None
                entry_pos = None
                entry_cost = 0.0
                equity_at_entry = pnl

        pos = new_pos
        poss.append(pos)
        equities.append(pnl)

    d = d.iloc[1:].copy()
    d['pos'] = poss
    d['equity'] = equities

    # プロット: スプレッドとz、ポジション
    plt.figure(figsize=(12,6))
    ax1 = plt.gca()
    ax1.plot(d['timestamp'], d['s'], label='spread s=fgrd-last - bybit-last')
    ax1.plot(d['timestamp'], d['sma'], label='SMA', alpha=0.7)
    ax1.legend(loc='upper left')
    ax2 = ax1.twinx()
    ax2.plot(d['timestamp'], d['z'], color='tab:orange', label='z', alpha=0.6)
    ax2.axhline(Z_ENTRY, color='tab:red', linestyle='--', alpha=0.4)
    ax2.axhline(-Z_ENTRY, color='tab:green', linestyle='--', alpha=0.4)
    ax2.axhline(0.0, color='gray', linestyle=':')
    ax2.legend(loc='upper right')
    # ポジション帯
    y0 = d['s'].min()
    y1 = d['s'].max()
    for i, p in enumerate(d['pos']):
        if p != 0:
            ax1.axvspan(d['timestamp'].iloc[i], d['timestamp'].iloc[i], color='red' if p<0 else 'green', alpha=0.08)
    plt.xticks(rotation=90, fontsize=7)
    plt.tight_layout()
    plt.savefig(IMG / 'swap_spread_z_positions.png', dpi=150)
    plt.close()

    # エクイティカーブ
    plt.figure(figsize=(12,5))
    plt.plot(d['timestamp'], d['equity'], label='equity')
    plt.xticks(rotation=90, fontsize=7)
    plt.title('Pair-trade equity (swap)')
    plt.tight_layout()
    plt.savefig(IMG / 'pair_equity.png', dpi=150)
    plt.close()

    # サマリ
    if trades:
        tr = pd.DataFrame(trades)
        tr['direction'] = tr['entry_pos'].map({1:'FGRD_buy/Bybit_sell', -1:'FGRD_sell/Bybit_buy'})
        tr.to_csv(IMG / 'pair_trades.csv', index=False)
        # 集計
        num = len(tr)
        pnl_total = float(d['equity'].iloc[-1])
        wins = (tr['pnl_net'] > 0).sum()
        avg_pnl = float(tr['pnl_net'].mean())
        med_pnl = float(tr['pnl_net'].median())
        avg_dur = float(tr['duration_sec'].mean())
        # ドローダウン
        eq = d['equity'].values
        peak = np.maximum.accumulate(eq)
        dd = peak - eq
        max_dd = float(dd.max())
        # シャープ風（10秒ステップ→日次換算）
        step_pnl = pd.Series(eq).diff().dropna()
        mu = step_pnl.mean()
        sigma = step_pnl.std(ddof=0)
        steps_per_day = 8640
        sharpe = float((mu / sigma) * np.sqrt(steps_per_day)) if sigma > 0 else 0.0
        summary = pd.DataFrame([{
            'trades': num,
            'wins': int(wins),
            'win_rate': float(wins)/num if num>0 else 0.0,
            'avg_pnl': avg_pnl,
            'median_pnl': med_pnl,
            'final_equity': pnl_total,
            'max_drawdown': max_dd,
            'sharpe_like_daily': sharpe,
            'avg_duration_sec': avg_dur
        }])
        summary.to_csv(IMG / 'pair_backtest_summary.csv', index=False)
    else:
        pd.DataFrame([{'trades':0,'wins':0,'win_rate':0.0,'final_equity':float(d['equity'].iloc[-1])}]).to_csv(IMG / 'pair_backtest_summary.csv', index=False)


def backtest_oneway_fgrd_high(
    df: pd.DataFrame,
    z_entry: float = None,
    z_exit: float = None,
    max_hold_sec: int = None,
    taker_fee_swap: float = None,
    slippage_usd: float = None,
    unit: float = None,
    output_prefix: str = 'oneway',
    return_summary_only: bool = False,
    sma_window: int = None,
    std_window: int = None,
    persistence_n: int = 1,
    cooldown_sec: int = 0,
):
    """
    片方向戦略: FGRDの契約価格がBybitより"異常に高い"ときのみエントリー。
      エントリー: z > ONEWAY_Z_ENTRY で FGRD売り + Bybit買い（pos = -1）
      エグジット: z < ONEWAY_Z_EXIT または 保持時間 > MAX_HOLD_SEC
    PnL: dPnL = pos * Δs（s = fgrd - bybit）− コスト
    """
    d = df.copy()
    d['s'] = d['swap_fgrd_last'] - d['swap_bybit_last']
    # 窓幅（未指定時はデフォルト）
    swa = SMA_WINDOW if sma_window is None else sma_window
    stw = STD_WINDOW if std_window is None else std_window
    d['sma'] = d['s'].rolling(swa, min_periods=max(5, int(swa*0.2))).mean()
    d['std'] = d['s'].rolling(stw, min_periods=max(5, int(stw*0.2))).std(ddof=0)
    d['z'] = (d['s'] - d['sma']) / d['std']
    d['z'] = d['z'].replace([np.inf, -np.inf], np.nan).fillna(0.0)

    # パラメータ反映（未指定ならグローバル）
    z_entry = ONEWAY_Z_ENTRY if z_entry is None else z_entry
    z_exit = ONEWAY_Z_EXIT if z_exit is None else z_exit
    max_hold_sec = MAX_HOLD_SEC if max_hold_sec is None else max_hold_sec
    taker_fee_swap = TAKER_FEE_SWAP if taker_fee_swap is None else taker_fee_swap
    slippage_usd = SLIPPAGE_USD if slippage_usd is None else slippage_usd
    unit = UNIT if unit is None else unit

    pos = 0   # 0 or -1
    pnl = 0.0
    equities = []
    poss = []
    trades = []
    entry_idx = None
    entry_s = None
    entry_time = None
    equity_at_entry = 0.0

    def trade_cost(row):
        price_f = float(row['swap_fgrd_last']) * unit
        price_b = float(row['swap_bybit_last']) * unit
        fee = taker_fee_swap * (abs(price_f) + abs(price_b))
        slip = 2.0 * slippage_usd
        return fee + slip

    ts = pd.to_datetime(d['timestamp'])
    last_exit_time = None
    consec = 0
    for i in range(1, len(d)):
        row_prev = d.iloc[i-1]
        row = d.iloc[i]
        ds = float(row['s'] - row_prev['s']) * UNIT

        pnl += pos * ds

        z = float(row['z'])
        now = ts.iloc[i]
        new_pos = pos

        if pos == 0:
            consec = consec + 1 if z > z_entry else 0
            cooldown_ok = True
            if cooldown_sec and last_exit_time is not None:
                cooldown_ok = (now - last_exit_time).total_seconds() >= cooldown_sec
            if (consec >= persistence_n) and cooldown_ok:
                c = trade_cost(row)
                pnl -= c
                new_pos = -1
                entry_idx = i
                entry_s = float(row['s'])
                entry_time = now
                equity_at_entry = pnl
        else:
            hold_sec = (now - entry_time).total_seconds() if entry_time is not None else 0.0
            exit_signal = (z < z_exit) or (hold_sec > max_hold_sec)
            if exit_signal:
                c = trade_cost(row)
                pnl -= c
                trade_pnl = pnl - equity_at_entry
                trades.append({
                    'entry_idx': entry_idx,
                    'exit_idx': i,
                    'entry_s': entry_s,
                    'exit_s': float(row['s']),
                    'pnl_net': float(trade_pnl),
                    'cost_total': float(c),
                    'duration_sec': hold_sec,
                    'direction': 'FGRD_sell/Bybit_buy'
                })
                new_pos = 0
                entry_idx = None
                entry_s = None
                entry_time = None
                equity_at_entry = pnl
                last_exit_time = now

        pos = new_pos
        poss.append(pos)
        equities.append(pnl)

    d = d.iloc[1:].copy()
    d['pos'] = poss
    d['equity'] = equities

    # 出力
    if not return_summary_only:
        plt.figure(figsize=(12,5))
        plt.plot(d['timestamp'], d['equity'])
        plt.title(f'Equity ({output_prefix})')
        plt.xticks(rotation=90, fontsize=7)
        plt.tight_layout()
        plt.savefig(IMG / f'{output_prefix}_equity.png', dpi=150)
        plt.close()

    if trades:
        tr = pd.DataFrame(trades)
        if not return_summary_only:
            tr.to_csv(IMG / f'{output_prefix}_trades.csv', index=False)
        num = len(tr)
        pnl_total = float(d['equity'].iloc[-1])
        wins = int((tr['pnl_net'] > 0).sum())
        avg_pnl = float(tr['pnl_net'].mean())
        med_pnl = float(tr['pnl_net'].median())
        avg_dur = float(tr['duration_sec'].mean())
        # DD / Sharpe-like
        eq = d['equity'].values
        peak = np.maximum.accumulate(eq)
        dd = peak - eq
        max_dd = float(dd.max())
        step = pd.Series(eq).diff().dropna()
        mu = step.mean(); sigma = step.std(ddof=0)
        steps_per_day = 8640
        sharpe = float((mu / sigma) * np.sqrt(steps_per_day)) if sigma > 0 else 0.0
        summary_df = pd.DataFrame([{
            'trades': num,
            'wins': wins,
            'win_rate': wins/num if num>0 else 0.0,
            'avg_pnl': avg_pnl,
            'median_pnl': med_pnl,
            'final_equity': pnl_total,
            'max_drawdown': max_dd,
            'sharpe_like_daily': sharpe,
            'avg_duration_sec': avg_dur
        }])
        if return_summary_only:
            return summary_df
        else:
            summary_df.to_csv(IMG / f'{output_prefix}_summary.csv', index=False)
    else:
        summary_df = pd.DataFrame([{'trades':0,'wins':0,'win_rate':0.0,'final_equity':float(d['equity'].iloc[-1])}])
        if return_summary_only:
            return summary_df
        else:
            summary_df.to_csv(IMG / f'{output_prefix}_summary.csv', index=False)


def sweep_oneway_params(df: pd.DataFrame):
    z_entries = [2.0, 2.5, 3.0]
    z_exits = [0.2, 0.3]
    max_holds = [60, 120, 300]
    fees = [0.0006, 0.0003]
    slips = [0.5, 0.2]
    units = [1.0]
    results = []
    for ze in z_entries:
        for zx in z_exits:
            for mh in max_holds:
                for fee in fees:
                    for sl in slips:
                        for un in units:
                            summ = backtest_oneway_fgrd_high(
                                df,
                                z_entry=ze,
                                z_exit=zx,
                                max_hold_sec=mh,
                                taker_fee_swap=fee,
                                slippage_usd=sl,
                                unit=un,
                                return_summary_only=True,
                            )
                            s = summ.iloc[0].to_dict()
                            s.update({'z_entry':ze,'z_exit':zx,'max_hold':mh,'fee':fee,'slippage':sl,'unit':un})
                            results.append(s)
    res = pd.DataFrame(results)
    res.sort_values(['final_equity','win_rate','avg_pnl'], ascending=[False, False, False], inplace=True)
    res.to_csv(IMG / 'oneway_sweep.csv', index=False)
    res.head(20).to_csv(IMG / 'oneway_sweep_top20.csv', index=False)


def detect_premium_events(
    df: pd.DataFrame,
    sma_window: int = 6*60,   # 1時間（10秒粒度）
    std_window: int = 6*60,
    z_high: float = 2.5,
    z_low: float = 0.5,
    min_duration_sec: int = 20*60,  # 20分
):
    """
    FGRDがBybitより高くなり（z>z_high）、その状態がmin_duration_sec以上継続し、
    その後z<z_lowに戻る事象を検出。
    出力: premium_events.csv（start, end, duration_sec, max_z, peak_spread, area）
    """
    d = df.copy()
    d['s'] = d['swap_fgrd_last'] - d['swap_bybit_last']
    d['sma'] = d['s'].rolling(sma_window, min_periods=max(5, int(sma_window*0.2))).mean()
    d['std'] = d['s'].rolling(std_window, min_periods=max(5, int(std_window*0.2))).std(ddof=0)
    d['z'] = ((d['s'] - d['sma']) / d['std']).replace([np.inf,-np.inf], np.nan).fillna(0.0)
    ts = pd.to_datetime(d['timestamp'])

    events = []
    in_evt = False
    start_idx = None
    area = 0.0
    max_z = -1e9
    peak_s = None

    for i in range(len(d)):
        z = float(d['z'].iloc[i])
        if not in_evt:
            if z > z_high:
                in_evt = True
                start_idx = i
                area = 0.0
                max_z = z
                peak_s = float(d['s'].iloc[i])
        else:
            # 積分近似
            area += max(0.0, z - z_low)
            if z > max_z:
                max_z = z
                peak_s = float(d['s'].iloc[i])
            # 終了条件
            if z < z_low:
                dur = (ts.iloc[i] - ts.iloc[start_idx]).total_seconds()
                if dur >= min_duration_sec:
                    events.append({
                        'start': ts.iloc[start_idx].isoformat(),
                        'end': ts.iloc[i].isoformat(),
                        'duration_sec': dur,
                        'max_z': max_z,
                        'peak_spread': peak_s,
                        'area_over_low': area,
                    })
                in_evt = False
                start_idx = None
                area = 0.0
                max_z = -1e9
                peak_s = None

    ev = pd.DataFrame(events)
    ev.to_csv(IMG / 'premium_events.csv', index=False)
    return ev


def backtest_premium_events(
    df: pd.DataFrame,
    events: pd.DataFrame,
    taker_fee_swap: float = TAKER_FEE_SWAP,
    slippage_usd: float = SLIPPAGE_USD,
    unit: float = UNIT,
    z_low: float = 0.5,
    output_prefix: str = 'premium'
):
    """
    検出済みイベントを用いたバックテスト:
      - エントリー: event.start 時点（pos = -1: FGRD売り/Bybit買い）
      - エグジット: z < z_low までホールド（event.end 近傍）
      - PnL = pos * (s_exit - s_entry) * unit − 2 * コスト（往復）
    """
    d = df.copy()
    d['s'] = d['swap_fgrd_last'] - d['swap_bybit_last']
    # z再計算（exit条件のため）
    d['sma'] = d['s'].rolling(SMA_WINDOW, min_periods=max(5, int(SMA_WINDOW*0.2))).mean()
    d['std'] = d['s'].rolling(STD_WINDOW, min_periods=max(5, int(STD_WINDOW*0.2))).std(ddof=0)
    d['z'] = ((d['s'] - d['sma']) / d['std']).replace([np.inf,-np.inf], np.nan).fillna(0.0)
    ts = pd.to_datetime(d['timestamp'])

    def cost_at(i):
        price_f = float(d['swap_fgrd_last'].iloc[i]) * unit
        price_b = float(d['swap_bybit_last'].iloc[i]) * unit
        fee = taker_fee_swap * (abs(price_f) + abs(price_b))
        slip = 2.0 * slippage_usd
        return fee + slip

    trades = []
    for _, ev in events.iterrows():
        # 近いインデックスを探す
        start_time = pd.to_datetime(ev['start'])
        end_time = pd.to_datetime(ev['end'])
        # エントリーindex: start_time に最も近い時刻の行
        i_entry = int((ts - start_time).abs().argmin())
        # エグジットindex: start_time以降で z < z_low となる最初の点、なければ end_time 近傍
        after = d.iloc[i_entry:].copy()
        cond = after['z'] < z_low
        if cond.any():
            i_exit = i_entry + int(np.argmax(cond.values))
        else:
            i_exit = int((ts - end_time).abs().argmin())
        if i_exit <= i_entry:
            continue
        s_entry = float(d['s'].iloc[i_entry])
        s_exit = float(d['s'].iloc[i_exit])
        pnl_gross = (-1.0) * (s_exit - s_entry) * unit  # pos=-1
        pnl_net = pnl_gross - (cost_at(i_entry) + cost_at(i_exit))
        trades.append({
            'start': ts.iloc[i_entry].isoformat(),
            'end': ts.iloc[i_exit].isoformat(),
            'entry_idx': i_entry,
            'exit_idx': i_exit,
            's_entry': s_entry,
            's_exit': s_exit,
            'pnl_gross': pnl_gross,
            'pnl_net': pnl_net,
            'duration_sec': float((ts.iloc[i_exit] - ts.iloc[i_entry]).total_seconds())
        })

    tr = pd.DataFrame(trades)
    if not tr.empty:
        tr.to_csv(IMG / f'{output_prefix}_events_trades.csv', index=False)
        num = len(tr)
        wins = int((tr['pnl_net'] > 0).sum())
        final_equity = float(tr['pnl_net'].sum())
        avg_pnl = float(tr['pnl_net'].mean())
        med_pnl = float(tr['pnl_net'].median())
        avg_dur = float(tr['duration_sec'].mean())
        pd.DataFrame([{
            'trades': num,
            'wins': wins,
            'win_rate': wins/num if num>0 else 0.0,
            'final_equity': final_equity,
            'avg_pnl': avg_pnl,
            'median_pnl': med_pnl,
            'avg_duration_sec': avg_dur
        }]).to_csv(IMG / f'{output_prefix}_events_summary.csv', index=False)
    else:
        pd.DataFrame([{'trades':0,'wins':0,'win_rate':0.0,'final_equity':0.0}]).to_csv(IMG / f'{output_prefix}_events_summary.csv', index=False)
    return tr

if __name__ == '__main__':
    run()
    # 追加: ペアトレード検証（契約）
    df0 = load()
    df0 = compute_spreads(df0)
    backtest_swap_pair(df0)
    # 追加: 片方向（FGRDが高いときのみショート）
    backtest_oneway_fgrd_high(df0)
    # 追加: スイープ
    sweep_oneway_params(df0)
    # 追加: プレミアム持続イベント検出
    ev = detect_premium_events(df0)
    backtest_premium_events(df0, ev)


def plot_futures_spreads(df: pd.DataFrame):
    """
    BTC/USDT 先物（契約）のクロス取引所スプレッドの時系列をPNG出力。
      - spread_fgrd_bid_minus_bybit_ask = swap_fgrd_bid - swap_bybit_ask
      - spread_bybit_bid_minus_fgrd_ask = swap_bybit_bid - swap_fgrd_ask
    """
    d = df.copy()
    d['spread_fgrd_bid_minus_bybit_ask'] = d['swap_fgrd_bid'] - d['swap_bybit_ask']
    d['spread_bybit_bid_minus_fgrd_ask'] = d['swap_bybit_bid'] - d['swap_fgrd_ask']
    # 保存用CSV
    d[['timestamp','spread_fgrd_bid_minus_bybit_ask','spread_bybit_bid_minus_fgrd_ask']].to_csv(IMG / 'futures_spreads.csv', index=False)

    plt.figure(figsize=(12,6))
    plt.plot(d['timestamp'], d['spread_fgrd_bid_minus_bybit_ask'], label='FGRD bid - Bybit ask')
    plt.plot(d['timestamp'], d['spread_bybit_bid_minus_fgrd_ask'], label='Bybit bid - FGRD ask')
    plt.axhline(0.0, color='gray', linestyle=':')
    plt.xticks(rotation=90, fontsize=7)
    plt.title('Futures spreads (BTCUSDT): cross-exchange')
    plt.legend()
    plt.tight_layout()
    plt.savefig(IMG / 'futures_spreads.png', dpi=150)
    plt.close()


if __name__ == '__main__':
    # 既存メイン処理の呼び出し後にスプレッド図を追加出力
    pass
