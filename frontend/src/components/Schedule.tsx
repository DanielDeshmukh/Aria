import { AnimatePresence, motion } from "framer-motion";
import { BookOpen, Minus, Plus } from "lucide-react";
import { useState } from "react";
import { README_OUTLINE, REPO_TREE, SECTION_9 } from "../data/site";
import { CodeBlock, Kicker, Reveal, Section, SectionHead } from "./ui";
import { cn } from "../utils/cn";

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
    <Section id="repo" className="border-t border-line py-24 md:py-32">
      <SectionHead
        no="08"
        kicker="engineering notes"
        title={
          <>
            The repo is<br />the documentation
          </>
        }
        desc="Structure, README outline, and the design answers behind the big decisions — kept honest and current."
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Reveal>
          <CodeBlock title="Aria/ — repository structure (planned)" code={REPO_TREE} wrap={false} className="h-full" />
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
              <Kicker className="px-1">design answers · living document</Kicker>
              {SECTION_9.map((s, i) => (
                <Section9Item key={i} i={i} q={s.q} a={s.a} />
              ))}
              <p className="px-1 font-mono text-[10.5px] leading-relaxed text-ink2">
                Every claim here should hold up in a design review.
              </p>
            </div>
          </Reveal>
        </div>
      </div>
    </Section>
  );
}
