import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { cn } from "../utils/cn";
import type { CallSummary, TranscriptEntry } from "./useVoiceSession";

const HIGHLIGHTED_KEYS = new Set([
  "customer_intent",
  "order_id",
  "resolution_status",
  "call_summary",
]);

function SummaryJson({ summary }: { summary: CallSummary }) {
  const entries = Object.entries(summary);
  return (
    <pre className="overflow-x-auto rounded-xl border border-line bg-card p-4 font-mono text-[12.5px] leading-relaxed text-ink2">
      {"{"}
      {entries.map(([key, value], i) => (
        <span key={key}>
          {"\n  "}
          <span
            className={cn(
              "font-semibold",
              HIGHLIGHTED_KEYS.has(key) ? "text-pine" : "text-ink2",
            )}
          >
            {JSON.stringify(key)}
          </span>
          {": "}
          <span className="text-ink">
            {JSON.stringify(value, null, 2).replace(/\n/g, "\n  ")}
          </span>
          {i < entries.length - 1 ? "," : ""}
        </span>
      ))}
      {"\n}"}
    </pre>
  );
}

export default function SummaryCard({
  summary,
  transcript,
}: {
  summary: CallSummary;
  transcript: TranscriptEntry[];
}) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    const json = JSON.stringify(summary, null, 2);
    try {
      await navigator.clipboard.writeText(json);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = json;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  return (
    <section aria-label="call summary" className="rounded-2xl border border-line bg-card/70 p-5 md:p-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="font-display text-xl font-medium text-ink">Call summary</h2>
        <button
          type="button"
          onClick={copy}
          className="flex items-center gap-1.5 rounded-full border border-line bg-card px-3.5 py-1.5 font-mono text-[11px] uppercase tracking-[0.16em] text-ink2 transition-colors duration-300 hover:border-mint2 hover:text-pine"
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? "copied" : "copy json"}
        </button>
      </div>

      <SummaryJson summary={summary} />

      <div className="mt-6">
        <div className="mb-3 font-mono text-[11px] uppercase tracking-[0.24em] text-ink2">
          Transcript log
        </div>
        {transcript.length > 0 ? (
          <ol className="space-y-2.5">
            {transcript.map((entry, i) => (
              <li key={i} className="flex gap-3.5">
                <span
                  className={cn(
                    "w-10 shrink-0 pt-0.5 font-mono text-[10px] uppercase tracking-[0.2em]",
                    entry.role === "agent" ? "text-pine" : "text-ink2",
                  )}
                >
                  {entry.role === "agent" ? "Aria" : "You"}
                </span>
                <span
                  className={cn(
                    "text-[13.5px] leading-relaxed",
                    entry.role === "agent" ? "text-ink" : "text-ink2",
                    !entry.final && "italic",
                  )}
                >
                  {entry.text}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-[13px] text-ink2">No transcript recorded.</p>
        )}
      </div>
    </section>
  );
}
