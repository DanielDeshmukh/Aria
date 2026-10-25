import { Chip } from "../components/ui";
import CallControls from "./CallControls";
import LiveTranscript from "./LiveTranscript";
import OrdersPanel from "./OrdersPanel";
import StateBadge from "./StateBadge";
import SummaryCard from "./SummaryCard";
import { useVoiceSession } from "./useVoiceSession";

/**
 * The call surface itself — session state, transcript, orders helper,
 * summary and controls. Rendered both inside the landing page (embedded
 * below the hero) and on the standalone `/call` route shell (CallApp),
 * so both surfaces always stay in sync.
 */
export default function CallPanel() {
  const session = useVoiceSession();
  const { state, stats, error, notice, transcript, summary, tools } = session;

  return (
    <div>
      {/* live status row */}
      <div className="mb-5 flex flex-wrap items-center gap-2.5">
        {stats && <Chip tone="pine">first audio {stats.first_audio_ms} ms</Chip>}
        {stats?.tool_lookup_ms !== undefined && (
          <Chip>tool lookup {stats.tool_lookup_ms} ms</Chip>
        )}
        <StateBadge state={state} />
      </div>

      {error && (
        <div
          role="alert"
          className="mb-6 rounded-2xl border border-pop/40 bg-popsoft px-4 py-3.5 text-[13.5px] font-medium text-pop"
        >
          <p>{error}</p>
          {/microphone/i.test(error) && (
            <p className="mt-1.5 text-[12.5px] font-normal leading-relaxed text-pop/85">
              Retry re-prompts for the microphone. If the browser keeps blocking
              it, allow microphone access for this site in your browser
              settings, then retry.
            </p>
          )}
        </div>
      )}

      {notice && !error && (
        <div className="mb-5 rounded-2xl border border-line bg-card px-4 py-3 text-[13px] text-ink2">
          {notice}
        </div>
      )}

      {/* live transcript + orders helper */}
      <div className="grid gap-6 md:grid-cols-[1fr_330px]">
        <LiveTranscript transcript={transcript} tools={tools} />
        <OrdersPanel />
      </div>

      {/* post-call summary card */}
      {summary && (
        <div className="mt-6">
          <SummaryCard summary={summary} transcript={transcript} />
        </div>
      )}

      <div className="mt-7">
        <CallControls state={state} onStart={session.start} onEnd={session.end} onRetry={session.retry} />
      </div>
    </div>
  );
}
