import { motion } from "framer-motion";
import { ArrowRight, AudioLines, FileCheck2, ShieldAlert } from "lucide-react";
import { INTERVIEW, MATRIX, RISKS } from "../data/plan";
import { Kicker, Reveal, Section, SectionHead } from "./ui";

export default function Appendix() {
  return (
    <>
      {/* 14 · risks */}
      <Section id="appendix" className="border-t border-line py-24 md:py-32">
        <SectionHead
          no="14"
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

      {/* 15 · interview prep */}
      <Section id="interview" className="border-t border-line py-24 md:py-32">
        <SectionHead
          no="15"
          kicker="interview prep · say it back"
          title={
            <>
              Be ready to explain,
              <br />
              out loud
            </>
          }
          desc="AI tools are allowed — understanding is not optional. These six questions are the evaluation round."
          right={<AudioLines size={20} className="hidden text-ink2 md:block" />}
        />
        <div className="grid gap-3 md:grid-cols-2">
          {INTERVIEW.map((q, i) => (
            <Reveal key={i} delay={(i % 2) * 0.06}>
              <div className="group flex h-full items-start gap-4 rounded-2xl hairline bg-card p-5 transition-all duration-300 hover:-translate-y-1 hover:border-mint2">
                <span className="font-display text-3xl font-semibold text-mint2 transition-colors duration-300 group-hover:text-pine">
                  {(i + 1).toString().padStart(2, "0")}
                </span>
                <p className="pt-1 text-[14px] font-medium leading-snug text-ink">{q}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </Section>

      {/* appendix matrix */}
      <Section id="matrix" className="border-t border-line py-24 md:py-32">
        <SectionHead
          no="16"
          kicker="appendix · pdf cross-verification matrix"
          title={
            <>
              Every line of the PDF,
              <br />
              accounted for
            </>
          }
          desc="Each instruction in the Datastraw PDF, mapped to where this plan covers it. Nothing floats."
          right={<FileCheck2 size={20} className="hidden text-ink2 md:block" />}
        />
        <Reveal>
          <div className="overflow-hidden rounded-2xl hairline bg-card">
            <div className="max-h-[520px] overflow-y-auto">
              <table className="w-full min-w-[720px] text-left">
                <thead className="sticky top-0 bg-[#0f1c15]">
                  <tr className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-white/80">
                    <th className="w-24 px-6 py-3.5 font-medium">pdf §</th>
                    <th className="px-4 py-3.5 font-medium">requirement</th>
                    <th className="w-44 px-6 py-3.5 font-medium">covered in</th>
                  </tr>
                </thead>
                <tbody>
                  {MATRIX.map(([s, req, cover], i) => (
                    <tr key={i} className={`border-b border-line/60 transition-colors hover:bg-mint/25 ${i % 2 ? "bg-paper/40" : ""}`}>
                      <td className="px-6 py-3.5">
                        <span className="rounded bg-paper px-1.5 py-0.5 font-mono text-[11px] font-semibold text-pined">{s}</span>
                      </td>
                      <td className="px-4 py-3.5 text-[12.5px] leading-relaxed text-ink2">{req}</td>
                      <td className="px-6 py-3.5 font-mono text-[11px] text-ink">{cover}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="border-t border-line px-6 py-3.5">
              <Kicker>{MATRIX.length} rows · zero gaps · scroll the matrix</Kicker>
            </div>
          </div>
        </Reveal>
      </Section>
    </>
  );
}
