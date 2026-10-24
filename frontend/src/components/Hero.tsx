import { motion, useScroll, useTransform } from "framer-motion";
import { ArrowDown } from "lucide-react";
import { useRef } from "react";
import { TICKER } from "../data/plan";
import { HERO_STATS } from "../data/site";
import { Counter, Kicker, Reveal, Waveform, useMarqueePause } from "./ui";

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.055, delayChildren: 0.15 } },
};
const letterRise = {
  hidden: { y: "110%", opacity: 0, filter: "blur(10px)" },
  show: {
    y: "0%",
    opacity: 1,
    filter: "blur(0px)",
    transition: { duration: 0.9, ease: [0.22, 1, 0.36, 1] as const },
  },
};

export default function Hero() {
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const fade = useTransform(scrollYProgress, [0, 0.75], [1, 0]);
  const marquee = useMarqueePause();

  return (
    <section ref={ref} id="top" className="relative overflow-hidden pt-14">
      {/* backdrop */}
      <div className="dot-grid absolute inset-0" style={{ maskImage: "radial-gradient(ellipse 90% 70% at 50% 34%, black 30%, transparent 78%)", WebkitMaskImage: "radial-gradient(ellipse 90% 70% at 50% 34%, black 30%, transparent 78%)" }} />

      <motion.div style={{ opacity: fade }} className="relative">
        <div className="relative mx-auto flex min-h-[calc(100vh-3.5rem)] w-full max-w-6xl flex-col items-center justify-center px-5 pb-24 pt-16 md:px-10">
          {/* kicker */}
          <Reveal y={16}>
            <Kicker>
              <span className="pulse-dot inline-block h-1.5 w-1.5 rounded-full bg-pop" />
              Aura Skincare · AI voice support
            </Kicker>
          </Reveal>

          {/* wordmark */}
          <div className="mt-8 text-center">
            <motion.h1
              variants={container}
              initial="hidden"
              animate="show"
              className="overflow-hidden font-display text-[24vw] font-semibold leading-[0.86] tracking-[-0.045em] text-ink sm:text-[17vw] lg:text-[11.5rem]"
            >
              <span className="inline-block overflow-hidden pb-[0.06em] align-bottom">
                {"Aria".split("").map((c, i) => (
                  <motion.span key={i} variants={letterRise} className="inline-block">
                    {c}
                  </motion.span>
                ))}
              </span>
              <motion.span variants={letterRise} className="inline-block text-pine">.</motion.span>
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.7, duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
              className="mx-auto mt-6 max-w-xl text-balance text-[15px] leading-relaxed text-ink2 md:text-base"
            >
              A browser-based AI voice customer-support agent for{" "}
              <span className="font-semibold text-ink">Aura Skincare</span> — natural
              conversation, live order lookups, and answers that stay inside policy.
            </motion.p>
          </div>

          {/* waveform */}
          <motion.div
            initial={{ opacity: 0, scaleX: 0.6 }}
            animate={{ opacity: 1, scaleX: 1 }}
            transition={{ delay: 0.85, duration: 1, ease: [0.22, 1, 0.36, 1] }}
            className="mt-10 origin-center"
          >
            <Waveform bars={56} />
          </motion.div>

          {/* scroll cue */}
          <motion.a
            href="/lens"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 1.4 }}
            className="absolute bottom-7 left-1/2 flex -translate-x-1/2 flex-col items-center gap-2 text-ink2 transition-colors hover:text-pine"
          >
            <span className="font-mono text-[10px] uppercase tracking-[0.3em]">the product</span>
            <motion.span animate={{ y: [0, 6, 0] }} transition={{ repeat: Infinity, duration: 1.8, ease: "easeInOut" }}>
              <ArrowDown size={15} />
            </motion.span>
          </motion.a>
        </div>
      </motion.div>

      {/* stats band */}
      <div className="relative border-t border-line bg-card/60 backdrop-blur-sm">
        <div className="mx-auto grid w-full max-w-6xl grid-cols-2 divide-x divide-line md:grid-cols-4">
          {HERO_STATS.map((s, i) => (
            <div key={i} className="px-5 py-7 md:px-8">
              <div className="font-display text-4xl font-medium text-ink md:text-5xl">
                <Counter value={s.value} decimals={(s as { decimals?: number }).decimals ?? 0} prefix={(s as { prefix?: string }).prefix ?? ""} suffix={s.suffix} />
              </div>
              <div className="mt-1.5 text-[13px] font-semibold text-ink">{s.label}</div>
              <div className="font-mono text-[11px] text-ink2">{s.note}</div>
            </div>
          ))}
        </div>
      </div>

      {/* marquee */}
      <div className="relative overflow-hidden border-y border-line bg-paper py-3.5" {...marquee.marqueeProps}>
        <div ref={marquee.ref} className="marquee-track flex w-max items-center gap-10 pr-10">
          {[...TICKER, ...TICKER].map((t, i) => (
            <span key={i} className="flex items-center gap-10 font-mono text-[11.5px] uppercase tracking-[0.2em] text-ink2">
              <span className="whitespace-nowrap">{t}</span>
              <span className="h-1 w-1 rounded-full bg-pine" />
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
