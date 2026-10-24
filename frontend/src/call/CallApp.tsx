import { Chip } from "../components/ui";
import CallControls from "./CallControls";
import StateBadge from "./StateBadge";
import { useVoiceSession } from "./useVoiceSession";

export default function CallApp() {
  const session = useVoiceSession();
  const { state, stats, error } = session;

  return (
    <div className="relative isolate min-h-screen bg-paper font-sans text-ink">
      <div className="bg-dotgrid pointer-events-none absolute inset-0 -z-10" aria-hidden />

      <header className="relative border-b border-line bg-card/70 backdrop-blur-sm">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-x-5 gap-y-2 px-5 py-4 md:px-10">
          <a
            href="/"
            className="font-mono text-[11px] uppercase tracking-[0.28em] text-ink2 transition-colors hover:text-pine"
          >
            ← back to site
          </a>
          <h1 className="font-display text-lg font-medium text-ink">
            Aria <span className="text-pine">·</span> live call
          </h1>
          <div className="ml-auto flex items-center gap-2.5">
            {stats && <Chip tone="pine">first audio {stats.first_audio_ms} ms</Chip>}
            <StateBadge state={state} />
          </div>
        </div>
      </header>

      <main className="relative mx-auto w-full max-w-6xl px-5 pb-16 pt-8 md:px-10">
        {error && (
          <div
            role="alert"
            className="mb-6 rounded-2xl border border-pop/40 bg-popsoft px-4 py-3.5 text-[13.5px] font-medium text-pop"
          >
            {error}
          </div>
        )}

        {/* reserved transcript region — LiveTranscript (T17) */}
        <div
          aria-label="live transcript"
          className="min-h-[220px] rounded-2xl border border-line bg-card/60"
        />

        {/* Test Orders Helper panel (T16) */}
        <div data-testid="orders-panel" className="mt-6" />

        {/* Post-call summary card (T18) */}
        <div data-testid="summary-card" className="mt-6" />

        <div className="mt-7">
          <CallControls
            state={state}
            onStart={session.start}
            onEnd={session.end}
            onRetry={session.retry}
          />
        </div>
      </main>
    </div>
  );
}
