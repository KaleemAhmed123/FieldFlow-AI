import { Bot, CornerDownLeft, Terminal, User } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { copilotChat, type CopilotToolCall } from "@/lib/api";

// The admin copilot (build step 14): ask in plain English, Groq tool-calls over the SF + e-com MCP
// tools, and answers. `toolsUsed` is shown as a mini decision-trace under each answer — the same
// "show your work" idea as the pipeline. Read-only: the copilot never mutates state.

interface Msg {
  role: "user" | "assistant";
  text: string;
  tools?: CopilotToolCall[];
  truncated?: boolean;
  unavailable?: string[];
  error?: boolean;
}

const STARTERS = [
  "How many appointments are in each status?",
  "Which appointments are unassigned?",
  "What's the stock of PCB-492?",
];

function ToolTrace({ tools }: { tools: CopilotToolCall[] }) {
  return (
    <div className="mt-2 space-y-1 border-t border-border pt-2">
      <div className="flex items-center gap-1.5 text-faint">
        <Terminal className="h-3 w-3" />
        <span className="font-mono text-[9px] uppercase tracking-wide">
          tools used ({tools.length})
        </span>
      </div>
      {tools.map((t, i) => (
        <div key={i} className="rounded border border-border bg-bg px-2 py-1.5">
          <div className="font-mono text-[10px] text-fg">
            {t.name}
            <span className="text-faint">({JSON.stringify(t.args)})</span>
          </div>
          <p className="mt-0.5 line-clamp-3 break-words font-mono text-[10px] leading-snug text-muted">
            {t.result}
          </p>
        </div>
      ))}
    </div>
  );
}

function Bubble({ m }: { m: Msg }) {
  const mine = m.role === "user";
  return (
    <div className={mine ? "flex justify-end" : "flex justify-start"}>
      <div className={`flex max-w-[92%] gap-2 ${mine ? "flex-row-reverse" : ""}`}>
        <div className="mt-0.5 shrink-0 text-muted">
          {mine ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
        </div>
        <div
          className={`rounded-lg px-2.5 py-1.5 text-[12px] leading-snug ${
            mine
              ? "bg-accent/15 text-fg"
              : m.error
                ? "border border-risk/30 bg-risk/10 text-fg"
                : "border border-border bg-surface text-fg"
          }`}
        >
          <p className="whitespace-pre-wrap break-words">{m.text}</p>
          {m.tools && m.tools.length > 0 && <ToolTrace tools={m.tools} />}
          {m.unavailable && m.unavailable.length > 0 && (
            <p className="mt-1 font-mono text-[9px] text-warn">
              unavailable: {m.unavailable.join(", ")} (tools offline)
            </p>
          )}
          {m.truncated && (
            <p className="mt-1 font-mono text-[9px] text-warn">
              stopped at the tool-call limit
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export function CopilotChat() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function ask(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    setBusy(true);
    try {
      const r = await copilotChat(q);
      if (!r.available) {
        setMessages((m) => [...m, { role: "assistant", text: r.detail ?? "Copilot unavailable.", error: true }]);
      } else {
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            text: r.answer ?? "",
            tools: r.toolsUsed,
            truncated: r.truncated,
            unavailable: r.sourcesUnavailable,
          },
        ]);
      }
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", text: `Request failed: ${String(e)}`, error: true }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-3 p-3">
          {messages.length === 0 && (
            <div className="space-y-2">
              <p className="text-[11px] leading-snug text-muted">
                Ask about field-service jobs or spare-parts stock. The copilot reads live Salesforce
                + inventory over MCP — it never changes anything.
              </p>
              <div className="flex flex-col gap-1.5">
                {STARTERS.map((s) => (
                  <button
                    key={s}
                    onClick={() => ask(s)}
                    className="rounded border border-border bg-surface px-2.5 py-1.5 text-left text-[11px] text-muted hover:text-fg"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <Bubble key={i} m={m} />
          ))}
          {busy && (
            <div className="flex items-center gap-1.5 text-faint">
              <Bot className="h-3.5 w-3.5" />
              <span className="font-mono text-[11px]">thinking…</span>
            </div>
          )}
          <div ref={endRef} />
        </div>
      </ScrollArea>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void ask(input);
        }}
        className="flex shrink-0 items-center gap-2 border-t border-border p-3"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask the copilot…"
          disabled={busy}
          className="h-8 flex-1 rounded border border-border bg-bg px-2.5 text-[12px] text-fg outline-none placeholder:text-faint focus:border-accent/50"
        />
        <Button type="submit" variant="accent" size="sm" disabled={busy || !input.trim()}>
          <CornerDownLeft className="h-3.5 w-3.5" />
        </Button>
      </form>
    </div>
  );
}
