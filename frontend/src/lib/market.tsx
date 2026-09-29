import { createContext, useContext, useState, type ReactNode } from "react";

export const MARKETS = [
  { code: "NG", label: "Nigeria" },
  { code: "US", label: "USA" },
  { code: "UK", label: "UK" },
  { code: "GCC", label: "GCC" },
  { code: "MY", label: "Malaysia" },
  { code: "GLOBAL", label: "Global" },
] as const;
export type MarketCode = (typeof MARKETS)[number]["code"];

const Ctx = createContext<{ market: MarketCode; setMarket: (m: MarketCode) => void } | null>(null);
const KEY = "hss.market";

function initial(): MarketCode {
  try {
    const v = localStorage.getItem(KEY);
    if (v && MARKETS.some((m) => m.code === v)) return v as MarketCode;
  } catch {
    /* storage blocked */
  }
  return "GLOBAL";
}

export function MarketProvider({ children }: { children: ReactNode }) {
  const [market, set] = useState<MarketCode>(initial);
  const setMarket = (m: MarketCode) => {
    set(m);
    try {
      localStorage.setItem(KEY, m);
    } catch {
      /* ignore */
    }
  };
  return <Ctx.Provider value={{ market, setMarket }}>{children}</Ctx.Provider>;
}

export function useMarket() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useMarket outside MarketProvider");
  return c;
}
