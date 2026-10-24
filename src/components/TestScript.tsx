import { motion } from "framer-motion";
import { CornerDownRight, Mic } from "lucide-react";
import { SCENARIOS } from "../data/plan";
import { Chip, Section, SectionHead } from "./ui";

const SPECIAL: Record<number, { label: string; tone: "pine" | "pop" | "warm" }> = {
  3: { label: "the only yes", tone: "pine" },
  5: { label: "COD limit", tone: "warm" },
  6: { label: "out of scope", tone: "pop" },
  7: { label: "barge-in", tone: "pine" },
  8: { label: "hinglish", tone: "pine" },
  11: { label: "no hallucination", tone: "pop" },
  12: { label: "₹499 boundary", tone: "pop" },
  13: { label: "injection attack", tone: "pop" },
};

export default function TestScript() {
  return (
    <Section id="tests" className="py-24 md:py-32">
      <SectionHead
        no="08"
        kicker="test script = demo script"
        title={
          <>
            Say this.
            <br />
            Expect <span className="italic text-pine">that.</span>
          </>
        }
        desc="Fourteen scenarios that double as the demo-video script. Run every single one on the deployed URL — not just locally."
        right={<Chip tone="pop" className="hidden md:inline-flex">run on the live URL</Chip>}
      />

      <div className="grid gap-3 md:grid-cols-2">
        {SCENARIOS.map(([say, expected], i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-30px" }}
            transition={{ delay: (i % 2) * 0.06, duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
            whileHover={{ x: 4 }}
            className="group flex gap-4 rounded-2xl hairline bg-card p-5 transition-colors duration-300 hover:border-mint2"
          >
            <span className="font-mono text-[11px] text-ink2 transition-colors group-hover:text-pine">
              {(i + 1).toString().padStart(2, "0")}
            </span>
            <div className="min-w-0">
              <div className="flex items-start gap-2">
                <Mic size={13} className="mt-1 shrink-0 text-pine" />
                <p className="font-display text-[15px] font-medium italic leading-snug text-ink">“{say}”</p>
              </div>
              <div className="mt-2.5 flex items-start gap-2 pl-[21px]">
                <CornerDownRight size={13} className="mt-0.5 shrink-0 text-ink2" />
                <p className="text-[12.5px] leading-relaxed text-ink2">{expected}</p>
              </div>
              {SPECIAL[i] && (
                <div className="mt-3 pl-[21px]">
                  <Chip tone={SPECIAL[i].tone}>{SPECIAL[i].label}</Chip>
                </div>
              )}
            </div>
          </motion.div>
        ))}
      </div>
    </Section>
  );
}
