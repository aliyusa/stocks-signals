export type DataStatus = "LIVE" | "DELAYED" | "END_OF_DAY" | "STALE" | "UNAVAILABLE";
export type ShariahStatus = "COMPLIANT" | "NON_COMPLIANT" | "QUESTIONABLE" | "INSUFFICIENT_DATA" | "UNDER_REVIEW";
export type SignalType = "BUY_SETUP" | "SELL_EXIT" | "HOLD" | "WAIT" | "AVOID" | "WATCHLIST";

export interface DataPoint<T> {
  value: T | null;
  source: string | null;
  as_of: string | null;
  frequency: string | null;
  status: DataStatus;
  note?: string | null;
}

export interface User {
  id: number;
  email: string;
  full_name: string | null;
  timezone: string;
  is_admin: boolean;
}

export interface SignalRow {
  id: number;
  ticker: string;
  name: string;
  signal: SignalType;
  score: number | null;
  coverage: number | null;
  risk_reward: number | null;
  data_as_of: string;
  created_at: string;
}

export interface Dashboard {
  generated_at: string;
  index_cards: { market: string; label: string; symbol: string; change_pct: DataPoint<number> & { level?: number } }[];
  counts: {
    stock_universe: number;
    shariah_compliant: number;
    potential_setups: number;
    watchlist_stocks: number;
    unread_alerts: number;
  };
  top_setups: SignalRow[];
  recent_signals: SignalRow[];
  market_regime: Record<string, DataPoint<string>>;
  data_sources: {
    code: string;
    name: string;
    kind: string;
    tier: string;
    frequency: string;
    enabled: boolean;
    last_success_at: string | null;
    last_error: string | null;
    status: DataStatus;
  }[];
}

export interface Quote {
  price: number | null;
  change_pct: number | null;
  as_of: string | null;
  status: DataStatus;
  source: string | null;
  frequency: string | null;
  note: string | null;
  volume?: number | null;
  previous_close?: number | null;
}

export interface StockRow {
  ticker: string;
  name: string;
  exchange: string;
  exchange_name: string;
  market: string;
  country: string | null;
  currency: string | null;
  type: string;
  isin: string | null;
  sector: string | null;
  quote: Quote;
}

export interface Usage {
  source: string;
  day: string;
  used: number;
  limit: number;
  remaining: number;
}

export interface StockDetail extends StockRow {
  refresh: { status: string; new_bars: number; message: string | null } | null;
  data_quality: {
    bars: number;
    first: string | null;
    last: string | null;
    zero_range_share_60: number | null;
    warnings: string[];
  };
  last_bar: string | null;
  usage: Usage;
}

export interface BarsResponse {
  ticker: string;
  exchange: string;
  interval: string;
  range: string;
  adjusted: boolean;
  note: string;
  bars: { t: string; o: number | null; h: number | null; l: number | null; c: number; ac: number | null; v: number | null }[];
}

// ---------- Phase 3: analysis ----------
export interface Rule { id: string; category: string; label: string; passed: boolean | null; value: string | null; detail: string }
export interface LevelOut { name: string; price: number | null; method: string }
export interface CategoryScore { label: string; weight: number; rules: number; evaluated: number; passed: number; pct: number | null; points: number | null }
export interface Regime { label: string | null; volatility?: string | null; explanation: string; index?: string; as_of?: string }

export interface SignalResult {
  as_of: string; close: number; signal_type: SignalType; score: number | null; coverage: number;
  breakdown: Record<string, CategoryScore>; rules: Rule[]; reasons: string[]; warnings: string[];
  entry_low: number | null; entry_high: number | null; stop: number | null; targets: LevelOut[];
  risk_reward: number | null; level_notes: LevelOut[];
  supports: { price: number; touches: number }[]; resistances: { price: number; touches: number }[];
  snapshot: Record<string, number | string | boolean | null> & { regime?: Regime | null };
  timeframes: Record<string, string>; summary: string;
}

export interface IndicatorSeries {
  t: string[];
  sma20: (number | null)[]; sma50: (number | null)[]; sma200: (number | null)[]; ema21: (number | null)[];
  bb_up: (number | null)[]; bb_mid: (number | null)[]; bb_lo: (number | null)[];
  rsi: (number | null)[]; macd: (number | null)[]; macd_signal: (number | null)[]; macd_hist: (number | null)[];
}

export type AnalysisResponse =
  | { available: false; reason: string }
  | { available: true; strategy: string; signal: SignalResult; series: IndicatorSeries };

export interface SignalListRow {
  ticker: string; name: string | null; exchange: string; currency: string | null; signal: SignalType;
  score: number | null; coverage: number | null; entry_low: number | null; entry_high: number | null;
  stop: number | null; target1: number | null; risk_reward: number | null; data_as_of: string; created_at: string;
  warnings: string[];
}

export interface ScanRow {
  ticker: string; name: string | null; exchange: string; market: string; currency: string | null; close: number;
  as_of: string; signal: SignalType; score: number | null; coverage: number; rsi: number | null; trend: string | null;
  volume_ratio: number | null; risk_reward: number | null; shariah: string; matched: string[];
}
export interface ScanResponse { scanned: number; skipped_short_history: number; results: ScanRow[]; note: string }

export interface Scoring {
  strategy: string; custom: boolean; weights: Record<string, number>; defaults: Record<string, number>;
  labels: Record<string, string>; params: Record<string, number>; liquidity_thresholds: Record<string, number>;
}
