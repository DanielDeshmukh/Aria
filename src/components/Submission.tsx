import { motion } from "framer-motion";
import { Clapperboard, Headphones, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { DEMO_PLAN, DEMO_TIPS, PRESUBMIT } from "../data/plan";
import { CheckRow, Chip, Reveal, Section, SectionHead } from "./ui";
import { cn } from "../utils/cn";

/* ---------------- demo timeline ---------------- */
function DemoTimeline() {
  return (
    <div className="relative">
      <span className="absolute bottom-4 left-[7px] top-4 w-px bg-line" />
      <motion.span
        initial={{ scaleY: 0 }}
        whileInView={{ scaleY: 1 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 1.6, ease: [0.22, 1, 0.36, 1] }}
        className="absolute bottom-4 left-[7px] top-4 w-px origin-top bg-pine"
      />
      <div className="space-y-3">
        {DEMO_PLAN.map((d, i) => (
          <motion.div
            key={d.t}
            initial={{ opacity: 0, x: -14 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-30px" }}
            transition={{ delay: i * 0.07, duration: 0.5 }}
            className="group relative flex items-start gap-5 pl-0"
          >
            <span className="relative z-10 mt-[18px] h-[15px] w-[15px] shrink-0 rounded-full border-[3px] border-paper bg-pine ring-1 ring-line transition-transform duration-300 group-hover:scale-125" />
            <div className="flex flex-1 flex-wrap items-center gap-3 rounded-xl hairline bg-card px-4 py-3.5 transition-colors group-hover:border-mint2">
              <span className="rounded-md bg-[#0f1c15] px-2 py-1 font-mono text-[11px] tabular text-[#c9e8d5]">{d.t}</span>
              <span className="text-[13px] leading-relaxed text-ink">{d.what}</span>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

/* ---------------- pre-submit checklist ---------------- */
function PreSubmit() {
  const [checks, setChecks] = useState<Record<number, boolean>>({});
  const done = useMemo(() => Object.values(checks).filter(Boolean).length, [checks]);
  const R = 46;
  const C = 2 * Math.PI * R;
  const all = done === PRESUBMIT.length;

  return (
    <div className="grid gap-8 lg:grid-cols-[300px_1fr]">
      <Reveal className="lg:sticky lg:top-24 lg:self-start">
        <div className="flex flex-col items-center rounded-2xl hairline bg-card p-8 text-center">
          <div className="relative h-32 w-32">
            <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
              <circle cx="60" cy="60" r={R} fill="none" stroke="var(--color-line)" strokeWidth="7" />
              <motion.circle
                cx="60" cy="60" r={R} fill="none"
                stroke={all ? "var(--color-pine)" : "var(--color-pop)"}
                strokeWidth="7" strokeLinecap="round"
                strokeDasharray={C}
                animate={{ strokeDashoffset: C - (done / PRESUBMIT.length) * C }}
                transition={{ type: "spring", stiffness: 60, damping: 16 }}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="font-display text-3xl font-semibold tabular text-ink">
                {Math.round((done / PRESUBMIT.length) * 100)}%
              </span>
              <span className="font-mono text-[9.5px] uppercase tracking-[0.2em] text-ink2">{done}/{PRESUBMIT.length} cleared</span>
            </div>
          </div>
          <p className={cn("mt-5 font-mono text-[11px] uppercase tracking-[0.22em]", all ? "text-pine" : "text-ink2")}>
            {all ? "go — send the email" : "clear every line"}
          </p>
          <p className="mt-2 text-[12px] leading-relaxed text-ink2">
            Wake the Space right before submitting, and again around when evaluators are likely to test.
          </p>
        </div>
      </Reveal>

      <div className="flex flex-col gap-2">
        {PRESUBMIT.map((p, i) => (
          <CheckRow key={i} index={i} checked={!!checks[i]} onToggle={() => setChecks((c) => ({ ...c, [i]: !c[i] }))}>
            {p}
          </CheckRow>
        ))}
      </div>
    </div>
  );
}

export default function Submission() {
  return (
    <>
      {/* 11 · demo video */}
      <Section id="submission" className="border-t border-line py-24 md:py-32">
        <SectionHead
          no="11"
          kicker="the 3–5 minute demo video"
          title={
            <>
              Four minutes,
              <br />
              five proofs
            </>
          }
          desc="Voice working, one order lookup, one policy conversation, the post-call transcript and JSON summary, and a brief architecture walkthrough — in that order."
        />
        <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
          <Reveal><DemoTimeline /></Reveal>
          <Reveal delay={0.1}>
            <div className="flex h-full flex-col gap-3">
              <div className="rounded-2xl hairline bg-card p-6">
                <div className="flex items-center gap-3">
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-mint text-pined"><Clapperboard size={16} /></span>
                  <h3 className="font-display text-lg font-medium tracking-tight">Recording rules</h3>
                </div>
                <p className="mt-3 text-[13px] leading-relaxed text-ink2">{DEMO_TIPS}</p>
              </div>
              <div className="rounded-2xl hairline bg-card p-6">
                <div className="flex items-center gap-3">
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-warmsoft text-warmup"><Headphones size={16} /></span>
                  <h3 className="font-display text-lg font-medium tracking-tight">Headphones on</h3>
                </div>
                <p className="mt-3 text-[13px] leading-relaxed text-ink2">
                  Both for you while recording and for the evaluators testing the live URL. It keeps echo out of the barge-in path.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Chip tone="pine">youtube unlisted</Chip>
                <Chip tone="pine">drive · link access</Chip>
                <Chip tone="pop">verify in incognito</Chip>
              </div>
            </div>
          </Reveal>
        </div>
      </Section>

      {/* 12 · pre-submit checklist */}
      <Section id="checklist" className="border-t border-line py-24 md:py-32">
        <SectionHead
          no="12"
          kicker="the pre-submit checklist"
          title={
            <>
              Ten lines between
              <br />
              you and <span className="italic text-pine">send</span>
            </>
          }
          desc="The final gate. Test on a different device and network, with the Space awake and credits to spare."
          right={<ShieldCheck size={20} className="hidden text-ink2 md:block" />}
        />
        <PreSubmit />
      </Section>
    </>
  );
}
