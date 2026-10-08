import { useQuery } from "@tanstack/react-query";

import { getDlq, getHealth, getMetricsText, getTools } from "@/lib/api";
import { toTiles } from "@/lib/metrics";

/** The controlled tool surface — rarely changes, so cache it longer. */
export function useTools() {
  return useQuery({ queryKey: ["tools"], queryFn: getTools, staleTime: 60_000 });
}

export function useDlq() {
  return useQuery({ queryKey: ["dlq"], queryFn: getDlq, refetchInterval: 3000 });
}

export function useMetrics() {
  return useQuery({
    queryKey: ["metrics"],
    queryFn: async () => toTiles(await getMetricsText()),
    refetchInterval: 2000,
  });
}

/** Backend reachability for the status dot. retry:false so a down backend shows immediately. */
export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: getHealth, refetchInterval: 5000, retry: false });
}
