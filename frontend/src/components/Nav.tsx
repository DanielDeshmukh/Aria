import { motion, useScroll, useSpring } from "framer-motion";
import { Moon, PhoneCall, Sun } from "lucide-react";
import { useState } from "react";
import { flushSync } from "react-dom";
import { NAV } from "../data/site";

function ThemeToggle() {
  const [dark, setDark] = useState(() =>
    document.documentElement.classList.contains("dark")
  );

  const toggle = (e: React.MouseEvent<HTMLButtonElement>) => {
    const next = !dark;

    const apply = () => {
      // flushSync so React commits before the "after" snapshot is taken
      flushSync(() => setDark(next));
      document.documentElement.classList.toggle("dark", next);
      try {
        localStorage.setItem("aria-theme", next ? "dark" : "light");
      } catch {}
    };

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (!document.startViewTransition || reduceMotion) {
      // no View Transitions: brief class-scoped crossfade (snap if reduced motion)
      const fade = !document.startViewTransition && !reduceMotion;
      if (fade) document.documentElement.classList.add("theme-fading");
      apply();
      if (fade) {
        window.setTimeout(() => {
          document.documentElement.classList.remove("theme-fading");
        }, 450);
      }
      return;
    }

    // circular reveal expanding from the button
    const { left, top, width, height } = e.currentTarget.getBoundingClientRect();
    const x = left + width / 2;
    const y = top + height / 2;
    const radius = Math.hypot(
      Math.max(x, window.innerWidth - x),
      Math.max(y, window.innerHeight - y)
    );

    const transition = document.startViewTransition(apply);
    transition.ready.then(() => {
      document.documentElement.animate(
        {
          clipPath: [
            `circle(0px at ${x}px ${y}px)`,
            `circle(${radius}px at ${x}px ${y}px)`,
          ],
        },
        {
          duration: 700,
          easing: "cubic-bezier(0.5, 1, 0.89, 1)",
          pseudoElement: "::view-transition-new(root)",
        }
      );
    });
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label="Toggle color theme"
      title={dark ? "Switch to light theme" : "Switch to dark theme"}
      className="group flex h-8 w-8 items-center justify-center justify-self-end rounded-full border border-line bg-paper/70 text-ink2 backdrop-blur-sm transition-colors hover:border-mint2 hover:text-pine"
    >
      <motion.span
        key={dark ? "sun" : "moon"}
        initial={{ rotate: -100, scale: 0.5 }}
        animate={{ rotate: 0, scale: 1 }}
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
              Aria <span className="text-ink2">/ voice agent</span>
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
