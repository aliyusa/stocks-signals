const TZ = "Africa/Lagos";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// DD MMM YYYY, HH:MM WAT (house style; avoids locale variants such as "Sept")
export function fmtDateTime(iso: string | null | undefined, empty = "Data unavailable"): string {
  if (!iso) return empty;
  const d = new Date(iso);
  const parts = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "numeric", year: "numeric", timeZone: TZ })
    .formatToParts(d)
    .reduce<Record<string, string>>((acc, p) => ({ ...acc, [p.type]: p.value }), {});
  const date = `${parts.day} ${MONTHS[Number(parts.month) - 1]} ${parts.year}`;
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: TZ });
  return `${date}, ${time} WAT`;
}

export function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return "n/a";
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return "n/a";
  return v.toLocaleString("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function fmtDate(iso: string | null | undefined, empty = "n/a"): string {
  if (!iso) return empty;
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d} ${MONTHS[Number(m) - 1]} ${y}`;
}

export function fmtMoney(v: number | null | undefined, currency: string | null | undefined): string {
  if (v === null || v === undefined) return "Data unavailable";
  const digits = Math.abs(v) >= 1000 ? 2 : Math.abs(v) >= 1 ? 2 : 4;
  return `${currency && currency !== "XXX" ? currency + " " : ""}${fmtNum(v, digits)}`;
}

export function fmtCompact(v: number | null | undefined): string {
  if (v === null || v === undefined) return "n/a";
  return new Intl.NumberFormat("en-GB", { notation: "compact", maximumFractionDigits: 2 }).format(v);
}
