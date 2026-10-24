import type { CallState } from "./useVoiceSession";

const ACTIVE_STATES: CallState[] = ["connecting", "listening", "thinking", "speaking"];
const START_STATES: CallState[] = ["idle", "ended", "error"];

export default function CallControls({
  state,
  onStart,
  onEnd,
  onRetry,
}: {
  state: CallState;
  onStart: () => void;
  onEnd: () => void;
  onRetry: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {START_STATES.includes(state) && (
        <button
          type="button"
          onClick={onStart}
          className="rounded-full bg-ink px-6 py-3 text-[13.5px] font-semibold text-paper transition-colors duration-300 hover:bg-pine"
        >
          {state === "ended" ? "Start a new call" : "Start Call"}
        </button>
      )}
      {ACTIVE_STATES.includes(state) && (
        <button
          type="button"
          onClick={onEnd}
          className="rounded-full border border-line bg-card px-6 py-3 text-[13.5px] font-semibold text-ink transition-colors duration-300 hover:border-pop/50 hover:text-pop"
        >
          End Call
        </button>
      )}
      {state === "error" && (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-full border border-pop/40 bg-popsoft px-6 py-3 text-[13.5px] font-semibold text-pop transition-colors duration-300 hover:border-pop hover:bg-pop hover:text-paper"
        >
          Retry
        </button>
      )}
    </div>
  );
}
