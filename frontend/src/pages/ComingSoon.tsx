import { NAV } from "../components/Layout";
import { Card } from "../components/ui";

const SCOPE: Record<string, string> = {
  "/markets": "Market overview per exchange, universal search, stock detail pages and candlestick charts.",
  "/scanner": "Filter by market, sector, Shariah status, RSI, MACD, trend, breakout, volume spike and setup score.",
  "/signals": "Explainable BUY SETUP, SELL / EXIT, HOLD, WAIT, AVOID and WATCHLIST signals with full score breakdown.",
  "/watchlist": "Multiple named watchlists with price, Shariah status, signal and last update.",
  "/portfolio": "Manually entered holdings, P/L, sector and market exposure. No trade execution.",
  "/backtesting": "Walk-forward backtests with costs and slippage and no look-ahead.",
  "/strategies": "Build, save and edit rule-based strategies.",
  "/alerts": "Price, indicator, score and entry-zone alerts via browser and email.",
  "/shariah": "Business-activity and ratio screening with the full 'Why?' breakdown.",
  "/risk": "Position sizing from account size, risk %, entry and stop.",
};

export default function ComingSoon({ path }: { path: string }) {
  const item = NAV.find((n) => n.to === path)!;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">{item.label}</h1>
      <Card>
        <p className="text-sm text-ink-300">Scheduled for <span className="font-semibold text-brand-500">Phase {item.phase}</span>.</p>
        <p className="mt-2 text-sm text-ink-400">{SCOPE[path]}</p>
      </Card>
    </div>
  );
}
