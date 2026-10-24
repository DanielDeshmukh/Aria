import { motion, useInView, useSpring, useTransform } from "framer-motion";
import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "../utils/cn";

/* ---------------- marquee: ease to a stop on hover ---------------- */
export function useMarqueePause() {
  const ref = useRef<HTMLDivElement | null>(null);
  const raf = useRef<number | null>(null);

  useEffect(() => () => {
    if (raf.current) cancelAnimationFrame(raf.current);
  }, []);

  const ramp = (target: number) => {
    const el = ref.current;
    if (!el) return;
    const anims = el.getAnimations();
    const anim = anims.find((a) => (a as CSSAnimation).animationName === "marquee") ?? anims[0];
    if (!anim) return;
    if (raf.current) cancelAnimationFrame(raf.current);
    const from = anim.playbackRate;
    if (from === target) return;
    if (target > 0 && anim.playState === "paused") anim.play();
    const start = performance.now();
    const dur = target === 0 ? 700 : 500;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / dur);
      const ease = 1 - Math.pow(1 - t, 3);
      const rate = from + (target - from) * ease;
      if (typeof anim.updatePlaybackRate === "function") anim.updatePlaybackRate(rate);
      else anim.playbackRate = rate;
      if (t < 1) raf.current = requestAnimationFrame(tick);
      else {
        raf.current = null;
        if (target === 0) anim.pause();
      }
    };
    raf.current = requestAnimationFrame(tick);
  };

  return {
    ref,
    marqueeProps: {
      onMouseEnter: () => ramp(0),
      onMouseLeave: () => ramp(1),
    },
  } as const;
}

/* ---------------- reveal on scroll ---------------- */
export function Reveal({
  children,
  delay = 0,
  y = 28,
  className,
}: {
  children: ReactNode;
  delay?: number;
  y?: number;
  className?: string;
}) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y, filter: "blur(8px)" }}
      whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.8, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}

/* ---------------- section shell ---------------- */
export function Section({
  id,
  className,
  children,
}: {
  id?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className={cn("relative mx-auto w-full max-w-6xl px-5 md:px-10", className)}>
      {children}
    </section>
  );
}

/* ---------------- section header ---------------- */
export function SectionHead({
  no,
  kicker,
  title,
  desc,
  right,
}: {
  no: string;
  kicker: string;
  title: ReactNode;
  desc?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className="mb-10 md:mb-14">
      <Reveal>
        <div className="flex items-baseline gap-4 md:gap-6">
          <span className="font-mono text-sm text-pine tabular">[{no}]</span>
          <span className="font-mono text-[11px] uppercase tracking-[0.28em] text-ink2">{kicker}</span>
          <span className="hidden h-px flex-1 bg-line md:block" />
          {right}
        </div>
      </Reveal>
      <div className="mt-5 flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
        <Reveal delay={0.08}>
          <h2 className="font-display text-4xl font-medium leading-[1.04] tracking-tight text-ink sm:text-5xl md:text-6xl text-balance">
            {title}
          </h2>
        </Reveal>
        {desc && (
          <Reveal delay={0.16} className="max-w-md">
            <p className="text-[15px] leading-relaxed text-ink2">{desc}</p>
          </Reveal>
        )}
      </div>
    </div>
  );
}

/* ---------------- kicker label ---------------- */
export function Kicker({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.28em] text-ink2",
        className
      )}
    >
      {children}
    </span>
  );
}

/* ---------------- chip ---------------- */
export function Chip({
  children,
  tone = "default",
  className,
}: {
  children: ReactNode;
  tone?: "default" | "pine" | "pop" | "warm";
  className?: string;
}) {
  const tones = {
    default: "border-line bg-card text-ink2",
    pine: "border-mint2 bg-mint text-pined",
    pop: "border-pop/40 bg-popsoft text-pop",
    warm: "border-warmup/40 bg-warmsoft text-warmup",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[11px] leading-none",
        tones[tone],
        className
      )}
    >
      {children}
    </span>
  );
}

/* ---------------- code block ---------------- */
export function CodeBlock({
  code,
  title,
  className,
  wrap = true,
}: {
  code: string;
  title?: string;
  className?: string;
  wrap?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = code;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };
  return (
    <div className={cn("overflow-hidden rounded-2xl border border-[#22362c] bg-[#0f1c15] shadow-[0_18px_50px_-24px_rgba(15,28,21,0.55)]", className)}>
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-[#284235]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#284235]" />
          <span className="h-2.5 w-2.5 rounded-full bg-pine" />
          {title && <span className="ml-3 font-mono text-[11px] text-emerald-100/50">{title}</span>}
        </div>
        <button
          onClick={copy}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 font-mono text-[11px] text-emerald-100/60 transition-colors hover:bg-white/5 hover:text-emerald-100"
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? "copied" : "copy"}
        </button>
      </div>
      <pre
        className={cn(
          "overflow-x-auto p-5 font-mono text-[12.5px] leading-relaxed text-[#c9e8d5]",
          !wrap && "whitespace-pre"
        )}
      >
        <code>{code}</code>
      </pre>
    </div>
  );
}

/* ---------------- interactive check row ---------------- */
export function CheckRow({
  checked,
  onToggle,
  children,
  index = 0,
}: {
  checked: boolean;
  onToggle: () => void;
  children: ReactNode;
  index?: number;
}) {
  return (
    <motion.button
      type="button"
      onClick={onToggle}
      initial={{ opacity: 0, x: -16 }}
      whileInView={{ opacity: 1, x: 0 }}
      viewport={{ once: true, margin: "-30px" }}
      transition={{ duration: 0.5, delay: index * 0.03, ease: [0.22, 1, 0.36, 1] }}
      whileTap={{ scale: 0.985 }}
      className={cn(
        "group flex w-full items-start gap-3.5 rounded-xl border px-4 py-3.5 text-left transition-all duration-300",
        checked
          ? "border-mint2 bg-mint/60"
          : "border-line bg-card hover:border-mint2 hover:bg-mint/25"
      )}
    >
      <span
        className={cn(
          "mt-0.5 flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[5px] border transition-all duration-300",
          checked ? "border-pine bg-pine" : "border-ink2/40 bg-card group-hover:border-pine"
        )}
      >
        <svg viewBox="0 0 12 12" className="h-3 w-3">
          <motion.path
            d="M2 6.4 4.8 9 10 3.2"
            fill="none"
            stroke="#fff"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            initial={false}
            animate={{ pathLength: checked ? 1 : 0, opacity: checked ? 1 : 0 }}
            transition={{ duration: 0.28, ease: "easeOut" }}
          />
        </svg>
      </span>
      <span
        className={cn(
          "text-[13.5px] leading-relaxed transition-colors duration-300",
          checked ? "text-pined" : "text-ink"
        )}
      >
        {children}
      </span>
    </motion.button>
  );
}

/* ---------------- animated counter ---------------- */
export function Counter({
  value,
  decimals = 0,
  prefix = "",
  suffix = "",
  className,
}: {
  value: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const mv = useSpring(0, { stiffness: 55, damping: 18 });
  const text = useTransform(mv, (v) => v.toFixed(decimals));
  const [out, setOut] = useState((0).toFixed(decimals));

  useEffect(() => {
    if (inView) mv.set(value);
  }, [inView, value, mv]);

  useEffect(() => {
    const unsub = text.on("change", (v) => setOut(v));
    return unsub;
  }, [text]);

  return (
    <span ref={ref} className={cn("tabular", className)}>
      {prefix}
      {out}
      {suffix}
    </span>
  );
}

/* ---------------- waveform (voice motif) ---------------- */
export function Waveform({
  bars = 40,
  className,
  color = "bg-pine",
  heights,
}: {
  bars?: number;
  className?: string;
  color?: string;
  heights?: number[];
}) {
  const hs =
    heights ??
    Array.from({ length: bars }, (_, i) => {
      const t = i / (bars - 1);
      return 18 + Math.abs(Math.sin(t * Math.PI * 3.2)) * 58 + Math.sin(t * Math.PI * 9) * 10;
    });
  return (
    <div className={cn("flex items-center gap-[3px]", className)} aria-hidden>
      {hs.map((h, i) => (
        <span
          key={i}
          className={cn("wave-bar w-[3px] rounded-full", color)}
          style={{ height: `${Math.max(8, h)}px`, animationDelay: `${(i % 14) * 0.09}s`, animationDuration: `${1.5 + (i % 5) * 0.17}s` }}
        />
      ))}
    </div>
  );
}
