import CallPanel from "./CallPanel";

/**
 * Standalone `/call` route: page chrome (back link, title) around the
 * shared CallPanel. The same panel is embedded in the landing page.
 */
export default function CallApp() {
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
        </div>
      </header>

      <main className="relative mx-auto w-full max-w-6xl px-5 pb-16 pt-8 md:px-10">
        <CallPanel />
      </main>
    </div>
  );
}
