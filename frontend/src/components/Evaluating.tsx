import { motion } from "framer-motion";
import { ArrowUpRight } from "lucide-react";
import { LENS_QUOTE } from "../data/plan";
import { LENS } from "../data/site";
import { Reveal, Section, SectionHead } from "./ui";

export default function Evaluating() {
  return (
    <Section id="lens" className="py-24 md:py-32">
      <SectionHead
        no="01"
        kicker="design principles"
        title={
          <>
            What this product
            <br />
            <span className="italic text-pine">lives</span> or dies on
          </>
        }
        desc="Four things. Not features, not polish for its own sake. Every decision in this build serves one of them — each only needs to prove itself once, cleanly, in a real conversation."
      />

      <div className="grid gap-4 sm:grid-cols-2">
        {LENS.map((c, i) => (
          <Reveal key={c.n} delay={i * 0.08}>
            <motion.div
              whileHover={{ y: -6 }}
              transition={{ type: "spring", stiffness: 260, damping: 22 }}
              className="group relative h-full overflow-hidden rounded-2xl hairline bg-card p-7 shadow-[0_2px_10px_-6px_rgba(19,32,25,0.12)] transition-colors duration-300 hover:border-mint2"
            >
              <span className="pointer-events-none absolute -right-3 -top-8 select-none font-display text-[7.5rem] font-semibold leading-none text-paper transition-colors duration-500 group-hover:text-mint">
                {c.n}
              </span>
              <div className="relative">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[11px] tracking-[0.22em] text-pine">SIGNAL {c.n}</span>
                  <ArrowUpRight
                    size={16}
                    className="text-ink2 opacity-0 transition-all duration-300 group-hover:translate-x-0.5 group-hover:text-pine group-hover:opacity-100"
                  />
                </div>
                <h3 className="mt-4 font-display text-2xl font-medium tracking-tight text-ink">{c.title}</h3>
                <p className="mt-2.5 max-w-md text-[13.5px] leading-relaxed text-ink2">{c.desc}</p>
              </div>
            </motion.div>
          </Reveal>
        ))}
      </div>

      {/* the one rule */}
      <Reveal delay={0.1} className="mt-16 md:mt-20">
        <figure className="relative border-y border-line py-12 text-center md:py-16">
          <span className="absolute -top-7 left-1/2 -translate-x-1/2 bg-paper px-4 font-display text-6xl italic text-pine">“</span>
          <blockquote className="mx-auto max-w-4xl text-balance font-display text-2xl font-light italic leading-snug tracking-tight text-ink md:text-[2.6rem] md:leading-[1.2]">
            {LENS_QUOTE}
          </blockquote>
          <figcaption className="mt-6 font-mono text-[11px] uppercase tracking-[0.3em] text-ink2">
            — how we scope features
          </figcaption>
        </figure>
      </Reveal>
    </Section>
  );
}
