import { ArrowUp, PhoneCall } from "lucide-react";
import { Reveal, Waveform, useMarqueePause } from "./ui";

export default function Footer() {
  const marquee = useMarqueePause();
  return (
    <footer className="relative mt-4 overflow-hidden bg-[#0b100d] text-white">
      {/* closing marquee */}
      <div className="overflow-hidden border-b border-white/10 py-3.5" {...marquee.marqueeProps}>
        <div ref={marquee.ref} className="marquee-slide flex w-max items-center gap-8 pr-8">
          {Array.from({ length: 2 }).flatMap((_, k) =>
            ["voice first", "policy true", "barge-in", "indian voice · hinglish", "order lookup", "transcript + summary"].map((t, i) => (
              <span key={`${k}-${i}`} className="flex items-center gap-8 font-mono text-[11px] uppercase tracking-[0.24em] text-white/50">
                <span className="whitespace-nowrap">{t}</span>
                <span className="h-1 w-1 rounded-full bg-pine" />
              </span>
            ))
          )}
        </div>
      </div>

      <div className="mx-auto w-full max-w-6xl px-5 py-20 md:px-10 md:py-28">
        <Reveal>
          <div className="flex flex-col items-start justify-between gap-10 md:flex-row md:items-end">
            <div>
              <span className="font-mono text-[11px] uppercase tracking-[0.3em] text-[#a5e8cd]">final word</span>
              <h2 className="mt-4 max-w-2xl text-balance font-display text-5xl font-medium leading-[1.02] tracking-tight md:text-7xl">
                Ship it live.
                <br />
                Keep it <span className="italic text-[#a5e8cd]">fast and honest.</span>
              </h2>
              <p className="mt-5 max-w-md text-[14px] leading-relaxed text-white/60">
                Requirements are the floor — every one answered in conversation, no promise
                outside policy, first audio inside the latency budget.
              </p>
            </div>
            <div className="flex flex-col items-start gap-5 md:items-end">
              <Waveform bars={22} color="bg-[#a5e8cd]" className="opacity-80" />
              <a
                href="/"
                className="group flex items-center gap-3 rounded-full border border-white/20 px-5 py-3 font-mono text-[11px] uppercase tracking-[0.22em] text-white/80 transition-all hover:border-[#a5e8cd] hover:text-[#a5e8cd]"
              >
                back to the top
                <ArrowUp size={14} className="transition-transform duration-300 group-hover:-translate-y-1" />
              </a>
            </div>
          </div>
        </Reveal>
      </div>

      <div className="border-t border-white/10">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-3 px-5 py-5 md:px-10">
          <span className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.22em] text-white/50">
            <PhoneCall size={12} className="text-[#a5e8cd]" />
            aria · voice support agent
          </span>
          <span className="font-mono text-[11px] text-white/40">
            aura skincare · react · fastapi
          </span>
        </div>
      </div>
    </footer>
  );
}
