import { ShieldAlert, ThumbsDown, ThumbsUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { needsApproval, rupees } from "@/lib/trace";

// Level-3 of the authority ladder: the human gate. Shows only when the case is paused for approval
// (low-confidence/risk-tier case, or a high-value quote). Approve/Reject resume via /sim/approve.
export function ApprovalActions({
  status,
  quoteAmountPaise,
  onDecide,
  pending,
}: {
  status: string;
  quoteAmountPaise?: number;
  onDecide: (approved: boolean) => void;
  pending: boolean;
}) {
  const kind = needsApproval(status);
  if (!kind) return null;

  return (
    <div className="animate-slide-in rounded-lg border border-warn/40 bg-warn/10 p-4">
      <div className="flex items-start gap-3">
        <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-warn" />
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-fg">
            {kind === "quote" ? "High-value quote needs approval" : "Human approval required"}
          </h3>
          <p className="mt-0.5 text-xs text-muted">
            {kind === "quote" ? (
              <>
                The quote is <span className="font-mono text-fg">{rupees(quoteAmountPaise)}</span> — above the
                auto-send threshold. Approve to send the Approve &amp; Pay card.
              </>
            ) : (
              "Confidence is below the gate (or the reason is risk-tiered), so nothing was sent. An operator decides before the customer sees anything."
            )}
          </p>
          <div className="mt-3 flex gap-2">
            <Button variant="accent" size="sm" disabled={pending} onClick={() => onDecide(true)}>
              <ThumbsUp className="h-3.5 w-3.5" /> Approve
            </Button>
            <Button variant="danger" size="sm" disabled={pending} onClick={() => onDecide(false)}>
              <ThumbsDown className="h-3.5 w-3.5" /> Reject
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
