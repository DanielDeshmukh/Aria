import { cn } from "../utils/cn";
import type { CallState } from "./useVoiceSession";

const LABELS: Record<CallState, string> = {
  idle: "ready",
  connecting: "connecting",
  listening: "listening",
  thinking: "thinking",
  speaking: "speaking",
  ended: "ended",
  error: "error",
};

function Indicator({ state }: { state: CallState }) {
  if (state === "listening") {
    return (
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-pine opacity-60" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-pine" />
      </span>
    );
  }
  if (state === "thinking") {
    return (
      <span className="flex items-center gap-[3px]">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-1 w-1 animate-bounce rounded-full bg-pine"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </span>
    );
  }
  if (state === "speaking") {
    return (
      <span className="flex h-2.5 items-end gap-[2px]">
        {[10, 7, 10].map((h, i) => (
          <span
            key={i}
            className="wave-bar w-[2px] rounded-full bg-pine"
            style={{ height: `${h}px`, animationDelay: `${i * 0.12}s` }}
          />
        ))}
      </span>
    );
  }
  if (state === "connecting") {
    return (
      <span className="h-2.5 w-2.5 animate-spin rounded-full border-2 border-ink2/40 border-t-pine" />
    );
  }
  return <span className="h-1.5 w-1.5 rounded-full bg-current opacity-60" />;
}

export default function StateBadge({ state }: { state: CallState }) {
  const accent =
    state === "error"
      ? "text-pop"
      : state === "listening" || state === "thinking" || state === "speaking"
        ? "text-pine"
        : "text-ink2";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border border-line bg-card px-3 py-1.5 font-mono text-[11px] uppercase leading-none tracking-[0.2em]",
        accent,
      )}
    >
      <Indicator state={state} />
      {LABELS[state]}
    </span>
  );
}
