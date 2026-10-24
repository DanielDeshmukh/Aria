import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useState } from "react";
import { SUMMARY_JSON } from "../data/plan";
import { REQUIREMENTS } from "../data/site";
import { CheckRow, Chip, CodeBlock, Reveal, Section, SectionHead } from "./ui";

const KEY_TAGS: Record<string, { label: string; tone: "pine" | "pop" | "warm" }> = {
  accent: { label: "accent + hinglish", tone: "pine" },
  latency: { label: "< 1.5s target", tone: "pop" },
  persona: { label: "persona", tone: "pine" },
  policy: { label: "must refuse", tone: "pop" },
  scope: { label: "out of scope", tone: "warm" },
  repeat: { label: "never guess", tone: "warm" },
  notfound: { label: "exact phrasing", tone: "pine" },
  tool: { label: "one tool, done well", tone: "pine" },
  json: { label: "structured output", tone: "pine" },
  state: { label: "visible state", tone: "pine" },
  transcript: { label: "live view", tone: "warm" },
};

export default function Requirements() {
  const [active, setActive] = useState("A");
  const [checks, setChecks] = useState<Record<string, boolean>>({});

  const total = useMemo(() => REQUIREMENTS.reduce((a, g) => a + g.items.length, 0), []);
  const done = useMemo(() => Object.values(checks).filter(Boolean).length, [checks]);
  const group = REQUIREMENTS.find((g) => g.id === active)!;

  return (
    <Section id="requirements" className="py-24 md:py-32">
      <SectionHead
        no="02"
        kicker="product spec · core requirements"
        title={
          <>
            Core requirements,
            <br />
            A <span className="font-display text-pine">→</span> E
          </>
        }
        desc="The contract for every call. Tick each line end-to-end on the deployed build — clicking here rehearses the acceptance pass."
        right={
          <div className="hidden items-center gap-3 font-mono text-[11px] text-ink2 md:flex">
            <span className="tabular">
              {done.toString().padStart(2, "0")} / {total.toString().padStart(2, "0")} ticked
            </span>
            <div className="h-1 w-28 overflow-hidden rounded-full bg-line">
              <motion.div
                className="h-full rounded-full bg-pine"
                animate={{ width: `${(done / total) * 100}%` }}
                transition={{ type: "spring", stiffness: 120, damping: 20 }}
              />
            </div>
          </div>
        }
      />

      <div className="grid gap-8 lg:grid-cols-[250px_1fr]">
        {/* tab rail */}
        <Reveal className="lg:sticky lg:top-24 lg:self-start">
          <div className="flex gap-2 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible">
            {REQUIREMENTS.map((g) => {
              const on = g.id === active;
              const groupDone = g.items.filter((_, i) => checks[`${g.id}-${i}`]).length;
              return (
                <button
                  key={g.id}
                  onClick={() => setActive(g.id)}
                  className="relative shrink-0 rounded-xl px-4 py-3 text-left lg:w-full"
                >
                  {on && (
                    <motion.span
                      layoutId="req-tab"
                      className="absolute inset-0 rounded-xl bg-ink"
                      transition={{ type: "spring", stiffness: 340, damping: 32 }}
                    />
                  )}
                  <span className="relative flex items-center gap-3">
                    <span
                      className={`flex h-7 w-7 items-center justify-center rounded-lg font-mono text-[12px] font-semibold ${
                        on ? "bg-pine text-white" : "hairline bg-card text-ink2"
                      }`}
                    >
                      {g.id}
                    </span>
                    <span className="min-w-0">
                      <span className={`block truncate text-[13px] font-semibold ${on ? "text-paper" : "text-ink"}`}>
                        {g.title}
                      </span>
                      <span className={`block font-mono text-[10px] ${on ? "text-paper/50" : "text-ink2"}`}>
                        {groupDone}/{g.items.length} · {g.tag}
                      </span>
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </Reveal>

        {/* items */}
        <div className="min-w-0">
          <AnimatePresence mode="wait">
            <motion.div
              key={active}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
              className="flex flex-col gap-2"
            >
              {group.items.map((it, i) => {
                const key = `${active}-${i}`;
                return (
                  <CheckRow
                    key={key}
                    index={i}
                    checked={!!checks[key]}
                    onToggle={() => setChecks((c) => ({ ...c, [key]: !c[key] }))}
                  >
                    <span className="flex flex-wrap items-center gap-2">
                      {it.text}
                      {it.key && KEY_TAGS[it.key] && (
                        <Chip tone={KEY_TAGS[it.key].tone}>{KEY_TAGS[it.key].label}</Chip>
                      )}
                    </span>
                  </CheckRow>
                );
              })}

              {active === "D" && (
                <div className="mt-4">
                  <CodeBlock title="post-call-summary.json — example shape" code={SUMMARY_JSON} />
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </Section>
  );
}
