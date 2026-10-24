import { motion, useScroll, useSpring } from "framer-motion";
import { Moon, PhoneCall, Sun } from "lucide-react";
import { useState } from "react";
import { NAV } from "../data/plan";

function ThemeToggle() {
  const [dark, setDark] = useState(() =>
    document.documentElement.classList.contains("dark")
  );

  const toggle = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("aria-theme", next ? "dark" : "light");
    } catch {}
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label="Toggle color theme"
      title={dark ? "Switch to light theme" : "Switch to dark theme"}
      className="group flex h-8 w-8 items-center justify-center justify-self-end rounded-full border border-line bg-card text-ink2 transition-colors hover:border-mint2 hover:text-pine"
    >
      <motion.span
        key={dark ? "sun" : "moon"}
        initial={{ rotate: -100, opacity: 0, scale: 0.5 }}
        animate={{ rotate: 0, opacity: 1, scale: 1 }}
        transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
        className="flex"
      >
        {dark ? <Sun size={14} strokeWidth={2.2} /> : <Moon size={14} strokeWidth={2.2} />}
      </motion.span>
    </button>
  );
}

export default function Nav() {
  const { scrollYProgress } = useScroll();
  const progress = useSpring(scrollYProgress, { stiffness: 120, damping: 24, mass: 0.4 });

  return (
    <header className="fixed inset-x-0 top-0 z-50">
      {/* scroll progress */}
      <motion.div className="h-[2.5px] origin-left bg-pine" style={{ scaleX: progress }} />
      <div className="border-b border-line bg-paper/85 backdrop-blur-md">
        <div className="grid h-14 w-full grid-cols-3 items-center px-4">
          <a href="/" className="group flex items-center gap-2.5 justify-self-start">
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-pine text-white transition-transform duration-500 group-hover:rotate-12">
              <PhoneCall size={13} strokeWidth={2.4} />
            </span>
            <span className="whitespace-nowrap font-mono text-[12px] font-medium uppercase tracking-[0.22em] text-ink">
              Aria <span className="text-ink2">/ master plan</span>
            </span>
          </a>

          <nav className="hidden items-center justify-center gap-5 lg:flex">
            {NAV.map((n) => (
              <a
                key={n.id}
                href={`/${n.id}`}
                className="u-link whitespace-nowrap text-[12.5px] font-medium text-ink2 transition-colors hover:text-ink"
              >
                {n.label}
              </a>
            ))}
          </nav>

          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
