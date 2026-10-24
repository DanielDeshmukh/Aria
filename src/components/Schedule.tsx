import { AnimatePresence, motion } from "framer-motion";
import { BookOpen, ChevronDown, Flag, Minus, Plus } from "lucide-react";
import { useState } from "react";
import { README_OUTLINE, REPO_TREE, SCHEDULE, SECTION_9 } from "../data/plan";
import { CodeBlock, Kicker, Reveal, Section, SectionHead } from "./ui";
import { cn } from "../utils/cn";

function DayCards() {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {SCHEDULE.map((d, i) => {
        const last = i === 3;
        return (
          <Reveal key={d.day} delay={i * 0.08}>
            <div
              className={cn(
                "flex h-full flex-col rounded-2xl p-6 transition-all duration-300 hover:-translate-y-1.5",
                last ? "border border-pop/30 bg-popsoft" : "hairline bg-card hover:border-mint2"
              )}
            >
              <div className="flex items-center justify-between">
                <span className={cn("font-mono text-[11px] uppercase tracking-[0.24em]", last ? "text-pop" : "text-pine")}>
                  {d.day}
                </span>
                <span className={cn("font-display text-4xl font-semibold", last ? "text-pop/20" : "text-mint2")}>
                  {i + 1}
                </span>
              </div>
              <h3 className="mt-3 font-display text-xl font-medium tracking-tight text-ink">{d.title}</h3>
              <p className="mt-2 flex-1 text-[12.5px] leading-relaxed text-ink2">{d.focus}</p>
              <div className={cn("mt-5 flex items-start gap-2.5 rounded-xl px-3.5 py-3", last ? "bg-card/70" : "bg-paper")}>
                <Flag size={13} className={cn("mt-0.5 shrink-0", last ? "text-pop" : "text-pine")} />
                <div>
                  <span className={cn("block font-mono text-[9.5px] uppercase tracking-[0.2em]", last ? "text-pop" : "text-pine")}>
                    exit criteria
                  </span>
                  <span className="block text-[12px] font-semibold leading-snug text-ink">{d.exit}</span>
                </div>
              </div>
            </div>
          </Reveal>
        );
      })}
    </div>
  );
}

function Section9Item({ i, q, a }: { i: number; q: string; a: string }) {
  const [open, setOpen] = useState(i === 0);
  return (
    <div className={cn("overflow-hidden rounded-2xl border transition-colors duration-300", open ? "border-mint2 bg-card" : "border-line bg-card/60")}>
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-4 px-5 py-4 text-left">
        <span className={cn("font-mono text-[11px]", open ? "text-pine" : "text-ink2")}>Q{i + 1}</span>
        <span className="flex-1 font-display text-[16px] font-medium tracking-tight text-ink">{q}</span>
        <motion.span animate={{ rotate: open ? 180 : 0 }} transition={{ duration: 0.3 }}>
          {open ? <Minus size={15} className="text-pine" /> : <Plus size={15} className="text-ink2" />}
        </motion.span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          >
            <p className="px-5 pb-5 pl-[52px] text-[13px] leading-relaxed text-ink2">{a}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function Schedule() {
  return (
    <>
      <Section id="schedule" className="border-t border-line py-24 md:py-32">
        <SectionHead
          no="09"
          kicker="the four-day schedule"
          title={
            <>
              Four days,
              <br />
              one <span className="italic text-pop">buffer</span>
            </>
          }
          desc="Each day has a hard exit criterion. Day 4 is protected: no new features, only packaging and submission."
          right={
            <span className="hidden items-center gap-2 font-mono text-[11px] text-ink2 md:flex">
              <ChevronDown size={13} className="rotate-[-90deg] text-pop" />
              expect ~1.5–2 days of focused work per the header
            </span>
          }
        />
        <DayCards />
      </Section>

      <Section id="repo" className="border-t border-line py-24 md:py-32">
        <SectionHead
          no="10"
          kicker="repository & readme"
          title={
            <>
              The repo is<br />the résumé
            </>
          }
          desc="Structure, README outline, and starter drafts for the four Section-9 answers — written in your own words before you submit."
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <Reveal>
            <CodeBlock title="aria-voice-agent/ — repository structure" code={REPO_TREE} wrap={false} className="h-full" />
          </Reveal>

          <div className="flex flex-col gap-4">
            <Reveal delay={0.06}>
              <div className="rounded-2xl hairline bg-card p-6">
                <div className="flex items-center gap-3">
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-mint text-pined">
                    <BookOpen size={16} />
                  </span>
                  <h3 className="font-display text-xl font-medium tracking-tight">README outline</h3>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {README_OUTLINE.map((r, i) => (
                    <span key={i} className="rounded-lg border border-line bg-paper px-3 py-2 text-[12px] font-medium text-ink2">
                      <span className="mr-1.5 font-mono text-[10px] text-pine">{i + 1}.</span>
                      {r}
                    </span>
                  ))}
                </div>
              </div>
            </Reveal>

            <Reveal delay={0.1}>
              <div className="flex flex-col gap-2.5">
                <Kicker className="px-1">section-9 answers · starting points — make them yours</Kicker>
                {SECTION_9.map((s, i) => (
                  <Section9Item key={i} i={i} q={s.q} a={s.a} />
                ))}
                <p className="px-1 font-mono text-[10.5px] leading-relaxed text-ink2">
                  They may ask follow-ups on every claim. Write only what you can defend.
                </p>
              </div>
            </Reveal>
          </div>
        </div>
      </Section>
    </>
  );
}
