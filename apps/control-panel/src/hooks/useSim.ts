import { useMutation, useQueryClient } from "@tanstack/react-query";

import * as api from "@/lib/api";

/** All /sim/* actions as mutations. On success they invalidate the polled reads so the UI catches
 *  up on the next tick (no manual refetch wiring in components). */
export function useSim() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["cases"] });
    qc.invalidateQueries({ queryKey: ["dlq"] });
    qc.invalidateQueries({ queryKey: ["metrics"] });
  };
  const opts = { onSuccess: invalidate };

  return {
    fireAtRisk: useMutation({ mutationFn: api.fireAtRisk, ...opts }),
    customerReply: useMutation({ mutationFn: api.customerReply, ...opts }),
    approve: useMutation({ mutationFn: api.approve, ...opts }),
    payment: useMutation({ mutationFn: api.payment, ...opts }),
    deliveryStatus: useMutation({ mutationFn: api.deliveryStatus, ...opts }),
    fault: useMutation({ mutationFn: api.fault, ...opts }),
    replayDlq: useMutation({ mutationFn: api.replayDlq, ...opts }),
  };
}
