import { motion } from "framer-motion";
import { ArrowRight, ShieldAlert } from "lucide-react";
import { RISKS } from "../data/site";
import { Section, SectionHead } from "./ui";

export default function Appendix() {
  return (
    <Section id="appendix" className="border-t border-line py-24 md:py-32">
      <SectionHead
        no="11"
        kicker="top risks & mitigations"
        title={
          <>
            What will try
            <br />
            to <span className="italic text-pop">break</span> this
          </>
        }
        desc="Name the failure modes before they happen. Each one already has an answer."
      />
      <div className="overflow-hidden rounded-2xl hairline bg-card">
        {RISKS.map(([risk, fix], i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-30px" }}
            transition={{ delay: i * 0.04, duration: 0.5 }}
            className={`grid gap-2 px-6 py-5 transition-colors hover:bg-mint/20 md:grid-cols-[1fr_28px_1fr] md:items-center md:gap-4 ${i !== RISKS.length - 1 ? "border-b border-line/70" : ""}`}
          >
            <div className="flex items-start gap-3">
              <ShieldAlert size={15} className="mt-0.5 shrink-0 text-pop" />
              <span className="text-[13.5px] font-semibold leading-snug text-ink">{risk}</span>
            </div>
            <ArrowRight size={14} className="hidden rotate-90 text-mint2 md:mx-auto md:block md:rotate-0" />
            <span className="pl-7 text-[13px] leading-relaxed text-ink2 md:pl-0">{fix}</span>
          </motion.div>
        ))}
      </div>
    </Section>
  );
}
