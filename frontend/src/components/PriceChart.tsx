import { Component, useEffect, useRef, type ReactNode } from "react";
import {
  ColorType, createChart, LineStyle, type IChartApi, type LogicalRange, type UTCTimestamp,
} from "lightweight-charts";
import type { BarsResponse, IndicatorSeries } from "../lib/types";
import { fmtDate, fmtNum } from "../lib/format";

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const iso = (t: unknown) => new Date((t as number) * 1000).toISOString().slice(0, 10);
// House style dates (DD MMM YYYY) on the crosshair and "Sep", never "Sept", on the axis.
const tick = (t: unknown, type: number) => {
  const d = new Date((t as number) * 1000);
  return type === 0 ? String(d.getUTCFullYear()) : type === 1 ? MON[d.getUTCMonth()] : `${d.getUTCDate()} ${MON[d.getUTCMonth()]}`;
};

const toTime = (d: string) => (Date.parse(`${d.slice(0, 10)}T00:00:00Z`) / 1000) as UTCTimestamp;

// Categorical overlay colours, validated for the dark chart surface #111823 (dataviz validator: all checks pass).
export const OVERLAYS = {
  sma20: { label: "SMA 20", color: "#3987e5" },
  sma50: { label: "SMA 50", color: "#d95926" },
  sma200: { label: "SMA 200", color: "#199e70" },
  ema21: { label: "EMA 21", color: "#c98500" },
  bb: { label: "Bollinger (20, 2)", color: "#d55181" },
} as const;
export type OverlayKey = keyof typeof OVERLAYS;

export interface PriceLevel { price: number; title: string; kind: "entry" | "stop" | "target" | "support" | "resistance" }
const LEVEL_STYLE: Record<PriceLevel["kind"], { color: string; style: LineStyle }> = {
  entry: { color: "#14b8a6", style: LineStyle.Solid },
  stop: { color: "#ef4444", style: LineStyle.Solid },
  target: { color: "#22c55e", style: LineStyle.Dashed },
  support: { color: "#8393a8", style: LineStyle.Dotted },
  resistance: { color: "#8393a8", style: LineStyle.Dotted },
};

const BASE = {
  layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#8393a8", fontSize: 11 },
  grid: { vertLines: { color: "#1b2636" }, horzLines: { color: "#1b2636" } },
  rightPriceScale: { borderColor: "#263346", minimumWidth: 72 },
  timeScale: { borderColor: "#263346", timeVisible: false, tickMarkFormatter: tick },
  crosshair: { mode: 0 },
  localization: { locale: "en-GB", timeFormatter: (t: unknown) => fmtDate(iso(t)), priceFormatter: (v: number) => fmtNum(v, 2) },
  autoSize: true,
} as const;

function line(series: IndicatorSeries, key: keyof IndicatorSeries) {
  const vals = series[key] as (number | null)[];
  return series.t.flatMap((t, i) => (vals[i] === null || vals[i] === undefined ? [] : [{ time: toTime(t), value: vals[i] as number }]));
}

interface Props {
  data: BarsResponse;
  height?: number;
  series?: IndicatorSeries;
  overlays?: OverlayKey[];
  levels?: PriceLevel[];
  panes?: ("rsi" | "macd")[];
}

function Chart({ data, height = 420, series, overlays = [], levels = [], panes = [] }: Props) {
  const main = useRef<HTMLDivElement>(null);
  const rsiEl = useRef<HTMLDivElement>(null);
  const macdEl = useRef<HTMLDivElement>(null);
  const key = JSON.stringify([overlays, levels, panes]);

  // One effect owns every chart's life cycle, so series are never touched after a chart is removed.
  useEffect(() => {
    if (!main.current) return;
    const charts: IChartApi[] = [];
    const c = createChart(main.current, { ...BASE, height });
    charts.push(c);
    const candles = c.addCandlestickSeries({
      upColor: "#22c55e", downColor: "#ef4444", borderVisible: false, wickUpColor: "#22c55e", wickDownColor: "#ef4444",
    });
    candles.priceScale().applyOptions({ scaleMargins: { top: 0.05, bottom: 0.25 } });
    const vol = c.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
    c.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    // Bars without full OHLC are drawn flat at the close; nothing is interpolated.
    candles.setData(data.bars.map((b) => ({
      time: toTime(b.t), open: b.o ?? b.c, high: b.h ?? b.c, low: b.l ?? b.c, close: b.c,
    })));
    vol.setData(data.bars.filter((b) => b.v !== null).map((b) => ({
      time: toTime(b.t), value: b.v as number, color: (b.o ?? b.c) <= b.c ? "#22c55e55" : "#ef444455",
    })));

    const opts = { lineWidth: 2 as const, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false };
    if (series) {
      for (const k of overlays) {
        if (k === "bb") {
          for (const b of ["bb_up", "bb_lo"] as const)
            c.addLineSeries({ ...opts, lineWidth: 1, color: OVERLAYS.bb.color, lineStyle: LineStyle.Dashed }).setData(line(series, b));
        } else {
          c.addLineSeries({ ...opts, color: OVERLAYS[k].color }).setData(line(series, k));
        }
      }
    }
    for (const l of levels) {
      const s = LEVEL_STYLE[l.kind];
      candles.createPriceLine({ price: l.price, color: s.color, lineStyle: s.style, lineWidth: 1, axisLabelVisible: true, title: l.title });
    }
    c.timeScale().fitContent();

    if (series && panes.includes("rsi") && rsiEl.current) {
      const r = createChart(rsiEl.current, { ...BASE, height: 120 });
      charts.push(r);
      const rs = r.addLineSeries({ ...opts, color: "#3987e5", lastValueVisible: true });
      rs.setData(line(series, "rsi"));
      for (const [p, t] of [[70, "70"], [50, "50"], [30, "30"]] as const)
        rs.createPriceLine({ price: p, color: "#5b6b82", lineStyle: LineStyle.Dotted, lineWidth: 1, axisLabelVisible: false, title: t });
      r.priceScale("right").applyOptions({ scaleMargins: { top: 0.08, bottom: 0.08 } });
      rs.applyOptions({ autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }) });
    }
    if (series && panes.includes("macd") && macdEl.current) {
      const m = createChart(macdEl.current, { ...BASE, height: 130 });
      charts.push(m);
      const hist = series.t.flatMap((t, i) => {
        const v = series.macd_hist[i];
        return v === null ? [] : [{ time: toTime(t), value: v, color: v >= 0 ? "#22c55e88" : "#ef444488" }];
      });
      m.addHistogramSeries({ lastValueVisible: false, priceLineVisible: false }).setData(hist);
      m.addLineSeries({ ...opts, color: "#3987e5" }).setData(line(series, "macd"));
      m.addLineSeries({ ...opts, color: "#d95926" }).setData(line(series, "macd_signal"));
    }

    // Keep the panes' time axes in step with the price chart.
    let syncing = false;
    const handlers = charts.map((src) => {
      const h = (range: LogicalRange | null) => {
        if (syncing || !range) return;
        syncing = true;
        charts.forEach((dst) => dst !== src && dst.timeScale().setVisibleLogicalRange(range));
        syncing = false;
      };
      src.timeScale().subscribeVisibleLogicalRangeChange(h);
      return h;
    });
    const r0 = c.timeScale().getVisibleLogicalRange();
    if (r0) charts.slice(1).forEach((x) => x.timeScale().setVisibleLogicalRange(r0));

    return () => {
      charts.forEach((x, i) => x.timeScale().unsubscribeVisibleLogicalRangeChange(handlers[i]));
      charts.forEach((x) => x.remove());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, series, height, key]);

  return (
    <div className="space-y-1">
      <div ref={main} className="w-full" style={{ height }} role="img" aria-label={`${data.ticker} daily candlestick chart with volume`} />
      {series && panes.includes("rsi") && (
        <div>
          <p className="px-1 text-[11px] text-ink-400">RSI (14) · reference lines at 30, 50 and 70</p>
          <div ref={rsiEl} className="w-full" style={{ height: 120 }} role="img" aria-label="RSI 14 pane" />
        </div>
      )}
      {series && panes.includes("macd") && (
        <div>
          <p className="flex flex-wrap items-center gap-3 px-1 text-[11px] text-ink-400">
            MACD (12, 26, 9)
            <Swatch color="#3987e5" label="MACD line" />
            <Swatch color="#d95926" label="Signal line" />
            <span>Histogram: green above zero, red below</span>
          </p>
          <div ref={macdEl} className="w-full" style={{ height: 130 }} role="img" aria-label="MACD pane" />
        </div>
      )}
    </div>
  );
}

export function Swatch({ color, label, dashed = false }: { color: string; label: string; dashed?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-ink-300">
      <span className="inline-block w-4" style={{ borderTop: `2px ${dashed ? "dashed" : "solid"} ${color}` }} aria-hidden />
      {label}
    </span>
  );
}

class ChartBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null as string | null };
  static getDerivedStateFromError(e: Error) {
    return { error: e.message };
  }
  render() {
    return this.state.error
      ? <p role="alert" className="text-sm text-red-400">The chart could not be drawn ({this.state.error}). The stored data is unaffected.</p>
      : this.props.children;
  }
}

export default function PriceChart(props: Props) {
  return <ChartBoundary><Chart {...props} /></ChartBoundary>;
}
