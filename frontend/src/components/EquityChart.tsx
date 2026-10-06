import { useEffect, useRef } from "react";
import { ColorType, createChart, type UTCTimestamp } from "lightweight-charts";
import { fmtDate, fmtNum } from "../lib/format";
import { Swatch } from "./PriceChart";

// Same validated categorical pair as the price-chart overlays (checked on surface #111823).
const STRATEGY = "#3987e5";
const BUY_HOLD = "#d95926";
const toTime = (d: string) => (Date.parse(`${d}T00:00:00Z`) / 1000) as UTCTimestamp;
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export default function EquityChart({ points, currency }: { points: { t: string; v: number; bh: number }[]; currency: string }) {
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!el.current || !points.length) return;
    const chart = createChart(el.current, {
      autoSize: true, height: 260,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#8393a8", fontSize: 11 },
      grid: { vertLines: { color: "#1b2636" }, horzLines: { color: "#1b2636" } },
      rightPriceScale: { borderColor: "#263346" },
      timeScale: { borderColor: "#263346", tickMarkFormatter: (t: unknown, type: number) => { const d = new Date((t as number) * 1000); return type === 0 ? String(d.getUTCFullYear()) : type === 1 ? MON[d.getUTCMonth()] : `${d.getUTCDate()} ${MON[d.getUTCMonth()]}`; } },
      localization: { locale: "en-GB", timeFormatter: (t: unknown) => fmtDate(new Date((t as number) * 1000).toISOString()), priceFormatter: (v: number) => fmtNum(v, 0) },
      crosshair: { mode: 0 },
    });
    const opts = { lineWidth: 2 as const, priceLineVisible: false, lastValueVisible: true };
    chart.addLineSeries({ ...opts, color: BUY_HOLD }).setData(points.map((p) => ({ time: toTime(p.t), value: p.bh })));
    chart.addLineSeries({ ...opts, color: STRATEGY }).setData(points.map((p) => ({ time: toTime(p.t), value: p.v })));
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [points]);
  return (
    <div>
      <p className="mb-2 flex flex-wrap items-center gap-4 text-[11px] text-ink-400">
        <Swatch color={STRATEGY} label="Strategy equity" /><Swatch color={BUY_HOLD} label="Buy and hold" /><span>{currency}, marked at each close</span>
      </p>
      <div ref={el} className="w-full" style={{ height: 260 }} role="img" aria-label="Equity curve of the strategy against buy and hold" />
    </div>
  );
}
