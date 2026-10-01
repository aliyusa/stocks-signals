export type DataStatus = "LIVE" | "DELAYED" | "END_OF_DAY" | "STALE" | "UNAVAILABLE";
export type ShariahStatus = "COMPLIANT" | "NON_COMPLIANT" | "QUESTIONABLE" | "INSUFFICIENT_DATA" | "UNDER_REVIEW" | "NOT_SCREENED";
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
  | { available: true; strategy: string; signal: SignalResult; series: IndicatorSeries;
      shariah: { status: ShariahStatus; methodology: string } };

export interface SignalListRow {
  ticker: string; name: string | null; exchange: string; currency: string | null; signal: SignalType;
  score: number | null; coverage: number | null; entry_low: number | null; entry_high: number | null;
  stop: number | null; target1: number | null; risk_reward: number | null; data_as_of: string; created_at: string;
  warnings: string[]; shariah: ShariahStatus;
}

export interface ScanRow {
  ticker: string; name: string | null; exchange: string; market: string; currency: string | null; close: number;
  as_of: string; signal: SignalType; score: number | null; coverage: number; rsi: number | null; trend: string | null;
  volume_ratio: number | null; risk_reward: number | null; shariah: ShariahStatus; matched: string[];
}
export interface ScanResponse { scanned: number; skipped_short_history: number; results: ScanRow[]; note: string; methodology: string }

export interface Scoring {
  strategy: string; custom: boolean; weights: Record<string, number>; defaults: Record<string, number>;
  labels: Record<string, string>; params: Record<string, number>; liquidity_thresholds: Record<string, number>;
}

// ---------- Phase 4: Shariah screening ----------
export type TestResult = "pass" | "fail" | "near" | "questionable" | "insufficient";

export interface Methodology {
  id: number; code: string; name: string; description: string; thresholds: Record<string, number>;
  prohibited_activities: string[]; denominator: string; max_data_age_days: number; is_builtin: boolean;
  owned: boolean; is_default?: boolean;
}

export interface Activity {
  tag: string; label?: string | null; primary: boolean; revenue_share: number | null; source?: string | null;
  as_of?: string | null;
}

export interface RatioResult {
  id: string; label: string; threshold: number; op: string; value: number | null; result: TestResult; note: string | null;
  numerator: { value: number | null; fields: string[]; note: string };
  denominator: { name: string; value: number | null; method: string | null; as_of: string | null };
}

export interface ShariahResult {
  status: Exclude<ShariahStatus, "NOT_SCREENED">; summary: string; reasons: string[]; warnings: string[];
  business: { result: TestResult; message: string | null; items: (Activity & { prohibited: boolean; result: TestResult; note: string })[] };
  ratios: RatioResult[];
  data: { period_end: string | null; period_type: string; currency: string | null; source: string | null; source_ref: string | null;
    is_estimate: boolean; reported_at: string | null; age_days: number | null; max_age_days: number; fresh: boolean } | null;
  purification: { ratio: number; per_share: number; dividend_per_share: number; currency: string | null; note: string } | null;
  external: ExternalOpinion[]; review_note: string | null; as_of: string; not_screened: boolean;
  methodology: { id: number; code: string; name: string; denominator: string; denominator_label: string };
  screen_id?: number; computed_at?: string;
}

export interface ExternalOpinion { source: string; status: "COMPLIANT" | "NON_COMPLIANT" | "QUESTIONABLE"; as_of: string; url?: string | null; note?: string | null }

export interface FundamentalsRow {
  id: number; period_end: string; period_type: string; currency: string | null; source: string | null; source_code: string | null;
  source_ref: string | null; note: string | null; is_estimate: boolean; reported_at: string | null; entered_at: string | null;
  [field: string]: number | string | boolean | null;
}

export interface StockShariah {
  ticker: string; exchange: string; currency: string | null; result: ShariahResult; activities: Activity[];
  external: ExternalOpinion[]; review_note: string | null; fundamentals: FundamentalsRow[];
  history: { id: number; status: ShariahStatus; methodology: string; computed_at: string; data_as_of: string | null }[];
  methodologies: { id: number; name: string }[]; disclaimer: string;
}

export interface Vocabulary {
  prohibited: { tag: string; label: string }[]; permissible: { tag: string; label: string }[];
  denominators: { key: string; label: string }[]; thresholds: { key: string; label: string }[];
  fundamental_fields: string[]; statuses: ShariahStatus[];
}

export interface ScreenerRow {
  ticker: string; name: string; exchange: string; status: ShariahStatus; primary: string | null;
  ratios: Record<string, { value: number | null; threshold: number; result: TestResult }>;
  period_end: string | null; fresh: boolean | null; first_reason: string | null;
}
export interface ScreenerResponse {
  methodology: Methodology; market: string; total: number; counts: Record<ShariahStatus, number>; results: ScreenerRow[]; note: string;
}
