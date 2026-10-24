import { motion } from "framer-motion";
import { ChevronRight, CircleSlash, MousePointerClick, Repeat2, ShieldCheck, Timer, Workflow } from "lucide-react";
import { useEffect, useState } from "react";
import { BARGE_IN, DB_FIELDS, DERIVED_FLAGS, EDGE_CASES, LATENCY, NORMALIZATION, TOOLS } from "../data/plan";
import { Chip, Kicker, Reveal, Section, SectionHead, Waveform } from "./ui";
import { cn } from "../utils/cn";

/* --------------------- live state machine --------------------- */

const CYCLE = ["idle", "connecting", "listening", "thinking", "speaking", "listening", "thinking", "speaking", "listening", "ended"];
const STATES = ["idle", "connecting", "listening", "thinking", "speaking", "ended"];

const STATE_STYLE: Record<string, { bg: string; text: string; dot: string }> = {
  idle: { bg: "bg-paper", text: "text-ink2", dot: "bg-ink2" },
  connecting: { bg: "bg-warmsoft", text: "text-warmup", dot: "bg-warmup" },
  listening: { bg: "bg-mint", text: "text-pined", dot: "bg-pine" },
  thinking: { bg: "bg-warmsoft", text: "text-warmup", dot: "bg-warmup" },
  speaking: { bg: "bg-mint", text: "text-pined", dot: "bg-pine" },
  ended: { bg: "bg-[#0f1c15]", text: "text-white", dot: "bg-mint2" },
};

function StateMachine() {
  const [step, setStep] = useState(0);
  const [paused, setPaused] = useState(false);
  const current = CYCLE[step % CYCLE.length];

  useEffect(() => {
    if (paused) return;
    const t = setInterval(() => setStep((s) => s + 1), 1350);
    return () => clearInterval(t);
  }, [paused]);

  return (
    <div
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      className="rounded-2xl hairline bg-card p-6 md:p-8"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Kicker>the state machine — cycling live {paused && "· paused"}</Kicker>
        <div className={cn("flex items-center gap-2 rounded-full px-3.5 py-1.5 font-mono text-[11px] uppercase tracking-[0.2em]", STATE_STYLE[current].bg, current === "ended" ? "text-white" : STATE_STYLE[current].text)}>
          <span className={cn("pulse-dot h-1.5 w-1.5 rounded-full", STATE_STYLE[current].dot)} />
          {current}
        </div>
      </div>

      <div className="mt-7 flex flex-wrap items-center gap-y-4">
        {STATES.map((s, i) => {
          const on = s === current;
          const seen = CYCLE.slice(0, (step % CYCLE.length) + 1).includes(s);
          return (
            <div key={s} className="flex items-center">
              <motion.div
                animate={{ scale: on ? 1.06 : 1 }}
                transition={{ type: "spring", stiffness: 300, damping: 20 }}
                className={cn(
                  "relative flex items-center gap-2.5 rounded-xl border px-4 py-2.5 font-mono text-[12px] transition-colors duration-300",
                  on
                    ? "border-pine bg-mint text-pined shadow-[0_10px_24px_-12px_rgba(11,122,91,0.55)]"
                    : seen
                      ? "border-mint2 bg-card text-ink"
                      : "border-line bg-card text-ink2"
                )}
              >
                {on && <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-pine" />}
                {s}
                {s === "speaking" && on && <Waveform bars={5} className="gap-[2px]" color="bg-pined" heights={[10, 16, 22, 14, 18]} />}
              </motion.div>
              {i < STATES.length - 1 && (
                <ChevronRight size={14} className={cn("mx-1.5", on ? "text-pine" : "text-line")} />
              )}
            </div>
          );
        })}
      </div>
      <p className="mt-5 font-mono text-[11px] leading-relaxed text-ink2">
        idle → connecting → listening → thinking → speaking → listening … → ended
        <span className="text-ink2/70"> · hover to pause the loop</span>
      </p>
    </div>
  );
}

/* --------------------- latency budget --------------------- */

function LatencyBar() {
  return (
    <div className="rounded-2xl hairline bg-card p-6 md:p-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Kicker>latency budget · end of speech → first audio</Kicker>
        <Chip tone="pop">target &lt; ~1.5s</Chip>
      </div>

      <div className="mt-6 flex h-14 w-full overflow-hidden rounded-xl border border-line bg-paper">
        {LATENCY.map((l, i) => (
          <motion.div
            key={l.label}
            initial={{ width: 0 }}
            whileInView={{ width: `${l.w}%` }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.9, delay: i * 0.18, ease: [0.22, 1, 0.36, 1] }}
            className={cn("relative flex items-center justify-center", l.cls)}
          >
            <span className="hidden font-mono text-[10.5px] font-medium text-white md:block">{l.ms}</span>
          </motion.div>
        ))}
        <motion.div
          initial={{ width: 0 }}
          whileInView={{ width: "20%" }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.9, delay: 0.6, ease: [0.22, 1, 0.36, 1] }}
          className="flex items-center justify-center"
          style={{ backgroundImage: "repeating-linear-gradient(135deg, #e1f2e7 0 6px, #f2faf5 6px 12px)" }}
        >
          <span className="font-mono text-[10.5px] text-pined">headroom</span>
        </motion.div>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-4">
        {[...LATENCY, { label: "buffer", ms: "~600 ms", cls: "bg-mint2" }].map((l) => (
          <div key={l.label} className="flex items-center gap-2 text-[12px]">
            <span className={cn("h-2.5 w-2.5 rounded-sm", l.cls)} />
            <span className="font-semibold text-ink">{l.label}</span>
            <span className="font-mono text-[11px] text-ink2">{l.ms}</span>
          </div>
        ))}
      </div>
      <p className="mt-4 border-t border-line pt-4 text-[12.5px] leading-relaxed text-ink2">
        STT endpointing ~300–500ms · LLM first token ~200–400ms · TTS first audio &lt;250ms.{" "}
        <span className="font-semibold text-ink">Play a short greeting immediately on Start Call</span> — the pipeline warms up behind it.
      </p>
    </div>
  );
}

/* --------------------- section --------------------- */

export default function ToolsBehavior() {
  return (
    <>
      {/* 06 · tools & policy engine */}
      <Section id="tools" className="py-24 md:py-32">
        <SectionHead
          no="06"
          kicker="tools & policy engine"
          title={
            <>
              One sharp tool,
              <br />
              enforced <span className="italic text-pine">in code</span>
            </>
          }
          desc="The LLM decides when to call; Python decides what's allowed. That split is the whole guardrail strategy."
        />

        <div className="grid gap-4 lg:grid-cols-2">
          {/* tools */}
          <Reveal>
            <div className="h-full overflow-hidden rounded-2xl hairline bg-card">
              <div className="flex items-center gap-3 border-b border-line px-6 py-4">
                <Workflow size={16} className="text-pine" />
                <span className="font-mono text-[11px] uppercase tracking-[0.24em] text-ink2">function calling surface</span>
              </div>
              {TOOLS.map((t) => (
                <div key={t.tool} className="border-b border-line/60 px-6 py-4 transition-colors last:border-0 hover:bg-mint/20">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="rounded-md bg-[#0f1c15] px-2 py-1 font-mono text-[11.5px] text-[#c9e8d5]">{t.tool}</span>
                    <Chip tone={t.req === "Required" ? "pop" : "default"}>{t.req}</Chip>
                  </div>
                  <p className="mt-2 text-[13px] leading-relaxed text-ink2">returns → {t.returns}</p>
                </div>
              ))}
              <div className="px-6 py-4">
                <p className="font-mono text-[11px] leading-relaxed text-ink2">
                  “Where is ORD-101?” → the LLM calls get_order_details → a natural spoken answer. Not the reverse.
                </p>
              </div>
            </div>
          </Reveal>

          {/* derived flags */}
          <Reveal delay={0.08}>
            <div className="flex h-full flex-col overflow-hidden rounded-2xl hairline bg-card">
              <div className="flex items-center gap-3 border-b border-line px-6 py-4">
                <ShieldCheck size={16} className="text-pine" />
                <span className="font-mono text-[11px] uppercase tracking-[0.24em] text-ink2">flags computed in code</span>
              </div>
              {DERIVED_FLAGS.map((f) => (
                <div key={f.flag} className="border-b border-line/60 px-6 py-4 transition-colors last:border-0 hover:bg-mint/20">
                  <span className="font-mono text-[13px] font-semibold text-ink">{f.flag}</span>
                  <p className="mt-1 text-[13px] leading-relaxed text-ink2">{f.rule}</p>
                </div>
              ))}
              <div className="mt-auto px-6 py-4">
                <span className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink2">mock db fields</span>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {DB_FIELDS.map((f) => (
                    <span key={f} className="rounded-md border border-line bg-paper px-2 py-1 font-mono text-[10.5px] text-ink2">{f}</span>
                  ))}
                </div>
              </div>
            </div>
          </Reveal>
        </div>

        {/* normalization */}
        <Reveal delay={0.05} className="mt-4">
          <div className="rounded-2xl border border-pop/30 bg-card p-6 md:p-8">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-popsoft text-pop">
                  <CircleSlash size={16} />
                </span>
                <h3 className="font-display text-xl font-medium tracking-tight">Order-ID normalization <span className="text-pop">(critical)</span></h3>
              </div>
              <Chip tone="pop">most likely to break in a live demo</Chip>
            </div>

            <div className="mt-6 flex flex-wrap items-center gap-2 font-mono text-[12px]">
              <span className="rounded-lg border border-line bg-paper px-3 py-2 text-ink2">“O R D one oh one”</span>
              {NORMALIZATION.steps.map((s) => (
                <span key={s} className="flex items-center gap-2">
                  <ChevronRight size={14} className="text-pop" />
                  <span className="rounded-lg border border-mint2 bg-mint/50 px-3 py-2 text-pined">{s}</span>
                </span>
              ))}
              <span className="flex items-center gap-2">
                <ChevronRight size={14} className="text-pop" />
                <span className="rounded-lg bg-[#0f1c15] px-3 py-2 font-semibold text-[#c9e8d5]">ORD-101</span>
              </span>
            </div>

            <p className="mt-5 max-w-3xl text-[13px] leading-relaxed text-ink2">{NORMALIZATION.note}</p>
          </div>
        </Reveal>
      </Section>

      {/* 07 · call behaviour */}
      <Section id="behaviour" className="border-t border-line py-24 md:py-32">
        <SectionHead
          no="07"
          kicker="call behaviour & edge cases"
          title={
            <>
              How the call
              <br />
              is allowed to feel
            </>
          }
          desc="A tight state machine, a hard latency budget, and interruption handled like a human conversation."
        />

        <div className="grid gap-4">
          <Reveal><StateMachine /></Reveal>

          <div className="grid gap-4 lg:grid-cols-2">
            <Reveal><LatencyBar /></Reveal>

            {/* barge-in */}
            <Reveal delay={0.08}>
              <div className="flex h-full flex-col rounded-2xl hairline bg-card p-6 md:p-8">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <Kicker>barge-in — worth doing</Kicker>
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-mint text-pined">
                    <Repeat2 size={15} />
                  </span>
                </div>
                <p className="mt-4 text-[13.5px] leading-relaxed text-ink2">{BARGE_IN}</p>
                <div className="mt-5 flex flex-col gap-2">
                  {["STT reports speech_start while speaking", "client stops playback · server cancels LLM + TTS streams", "state returns to listening"].map((s, i) => (
                    <div key={i} className="flex items-center gap-3 rounded-xl border border-line bg-paper px-4 py-3">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-card font-mono text-[10px] text-pined">{i + 1}</span>
                      <span className="text-[12.5px] font-medium text-ink">{s}</span>
                    </div>
                  ))}
                </div>
                <div className="mt-auto flex flex-wrap gap-2 pt-5">
                  <Chip tone="pine">echoCancellation: true</Chip>
                  <Chip tone="default">headphones recommended</Chip>
                </div>
              </div>
            </Reveal>
          </div>

          {/* edge cases */}
          <Reveal delay={0.05}>
            <div className="overflow-hidden rounded-2xl hairline bg-card">
              <div className="flex items-center gap-3 border-b border-line px-6 py-4">
                <MousePointerClick size={16} className="text-pine" />
                <span className="font-mono text-[11px] uppercase tracking-[0.24em] text-ink2">edge cases — handled explicitly</span>
              </div>
              <div className="grid md:grid-cols-2">
                {EDGE_CASES.map(([sit, exp], i) => (
                  <div
                    key={i}
                    className={cn(
                      "border-line/70 px-6 py-4 transition-colors hover:bg-mint/20",
                      i % 2 === 0 ? "md:border-r" : "",
                      i < EDGE_CASES.length - (EDGE_CASES.length % 2 === 0 ? 2 : 1) ? "border-b" : i !== EDGE_CASES.length - 1 ? "border-b md:border-b-0" : ""
                    )}
                  >
                    <div className="flex items-start gap-3">
                      <Timer size={13} className="mt-1 shrink-0 text-pop" />
                      <div>
                        <span className="block text-[13px] font-semibold text-ink">{sit}</span>
                        <span className="mt-0.5 block text-[12.5px] leading-relaxed text-ink2">{exp}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </Reveal>
        </div>
      </Section>
    </>
  );
}
