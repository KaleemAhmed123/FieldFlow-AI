// Parse Prometheus text exposition (what GET /metrics returns) into tiles for the strip.
// Format per line: `name value` or `name{label="x",..} value`; lines starting with # are metadata.

export interface Metric {
  name: string;
  value: number;
  labels?: Record<string, string>;
}

export function parseMetrics(text: string): Metric[] {
  const out: Metric[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const m = line.match(/^([a-zA-Z_:][\w:]*)(\{[^}]*\})?\s+(-?[\d.eE+]+|NaN|[+-]Inf)$/);
    if (!m) continue;
    const value = Number(m[3]);
    if (Number.isNaN(value)) continue;
    const labels: Record<string, string> = {};
    if (m[2]) {
      for (const pair of m[2].slice(1, -1).split(",")) {
        const [k, v] = pair.split("=");
        if (k) labels[k.trim()] = (v ?? "").trim().replace(/^"|"$/g, "");
      }
    }
    out.push({ name: m[1], value, labels: m[2] ? labels : undefined });
  }
  return out;
}

export interface MetricTile {
  key: string;
  label: string;
  value: number;
  tone: "accent" | "ok" | "warn" | "risk" | "info" | "muted";
}

// The known FieldFlow counters, in the order the strip should show them.
const KNOWN: Array<{ key: string; label: string; tone: MetricTile["tone"] }> = [
  { key: "fieldflow_events_processed_total", label: "Events processed", tone: "accent" },
  { key: "fieldflow_cards_sent_total", label: "RCS cards sent", tone: "info" },
  { key: "fieldflow_events_duplicate_total", label: "Duplicates ignored", tone: "muted" },
  { key: "fieldflow_sms_fallbacks_total", label: "SMS fallbacks", tone: "warn" },
  { key: "fieldflow_events_failed_total", label: "Failed → DLQ", tone: "risk" },
  { key: "fieldflow_dlq_replays_total", label: "DLQ replays", tone: "ok" },
];

/** Sum each metric across its label sets, then emit the known tiles (even at 0) in order. */
export function toTiles(text: string): MetricTile[] {
  const totals = new Map<string, number>();
  for (const m of parseMetrics(text)) {
    totals.set(m.name, (totals.get(m.name) ?? 0) + m.value);
  }
  return KNOWN.map((k) => ({ ...k, value: totals.get(k.key) ?? 0 }));
}
