import { useEffect, useRef } from "react";
import { cn } from "../utils/cn";
import type { ToolEvent, TranscriptEntry } from "./useVoiceSession";

type Row =
  | { kind: "line"; entry: TranscriptEntry }
  | { kind: "tool"; tool: ToolEvent };

function argsList(args: Record<string, unknown>): string {
  const values = Object.values(args).map((v) => String(v));
  return values.length ? values.join(", ") : "";
}

function resultSnippet(result: unknown): string {
  let text = "ok";
  if (typeof result === "string") {
    text = result;
  } else if (result && typeof result === "object") {
    const r = result as Record<string, unknown>;
    const order = r.order && typeof r.order === "object" ? (r.order as Record<string, unknown>) : null;
    if (order && typeof order.status === "string") text = order.status.toLowerCase();
    else if (r.found === false) text = typeof r.message === "string" ? r.message : "order not found";
    else if (typeof r.topic === "string") text = `${r.topic} policy`;
    else if (r.ok === true) text = "done";
    else if (typeof r.message === "string") text = r.message;
  }
  return text.length > 72 ? `${text.slice(0, 71).trimEnd()}…` : text;
}

function buildRows(transcript: TranscriptEntry[], tools: ToolEvent[]): Row[] {
  const rows: Row[] = [];
  const pending = [...tools];
  transcript.forEach((entry, i) => {
    rows.push({ kind: "line", entry });
    while (pending.length > 0 && pending[0].at <= i + 1) {
      const tool = pending.shift();
      if (tool) rows.push({ kind: "tool", tool });
    }
  });
  while (pending.length > 0) {
    const tool = pending.shift();
    if (tool) rows.push({ kind: "tool", tool });
  }
  return rows;
}

export default function LiveTranscript({
  transcript,
  tools,
}: {
  transcript: TranscriptEntry[];
  tools: ToolEvent[];
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const stick = useRef(true);
  const rows = buildRows(transcript, tools);
  const lastText = transcript[transcript.length - 1]?.text;

  useEffect(() => {
    const el = ref.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [rows.length, transcript.length, lastText]);

  const onScroll = () => {
    const el = ref.current;
    if (!el) return;
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
  };

  if (rows.length === 0) {
    return (
      <div
        aria-label="live transcript"
        className="flex min-h-[320px] items-center justify-center rounded-2xl border border-line bg-card/60 px-6 text-center"
      >
        <p className="font-mono text-[12px] uppercase tracking-[0.22em] text-ink2">
          Live transcript appears here…
        </p>
      </div>
    );
  }

  return (
    <div
      ref={ref}
      onScroll={onScroll}
      aria-label="live transcript"
      className="min-h-[320px] max-h-[560px] space-y-3.5 overflow-y-auto rounded-2xl border border-line bg-card/60 p-5"
    >
      {rows.map((row, i) =>
        row.kind === "tool" ? (
          <div
            key={`t${i}`}
            className="flex items-start gap-2 border-l-2 border-mint2 pl-3 font-mono text-[11.5px] leading-relaxed text-ink2"
          >
            <span className="text-pine">↳</span>
            <span className="min-w-0 break-words">
              {row.tool.name}({argsList(row.tool.args)}) → {resultSnippet(row.tool.result)}
            </span>
          </div>
        ) : (
          <div
            key={`l${i}`}
            className={cn(
              "border-l-2 pl-3.5",
              row.entry.role === "agent" ? "border-pine" : "border-line",
            )}
          >
            <div className="mb-0.5 font-mono text-[10px] uppercase tracking-[0.24em] text-ink2">
              {row.entry.role === "agent" ? "Aria" : "You"}
            </div>
            <p
              className={cn(
                "text-[14px] leading-relaxed",
                row.entry.role === "agent" ? "text-ink" : "text-ink2",
                !row.entry.final && "italic",
              )}
            >
              {row.entry.text}
            </p>
          </div>
        ),
      )}
    </div>
  );
}
