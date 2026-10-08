import { useQuery } from "@tanstack/react-query";

import { type CaseRow, getCases } from "@/lib/api";

export const POLL_MS = 1500;
export const casesKey = ["cases"] as const;

// THE LIVE-UPDATES SEAM. Today it polls GET /cases every POLL_MS (the backend is poll-only). To
// move to real push later, change only the internals here — subscribe to an SSE/WebSocket stream
// and write into the query cache under `casesKey`. No component needs to change.
export function useLiveCases() {
  return useQuery({ queryKey: casesKey, queryFn: getCases, refetchInterval: POLL_MS });
}

/** Select one case from the same polled list (GET /cases already carries the full trace). */
export function useCase(correlationId: string | null) {
  const q = useLiveCases();
  const current: CaseRow | undefined = correlationId
    ? q.data?.find((c) => c.correlationId === correlationId)
    : undefined;
  return { ...q, case: current };
}
