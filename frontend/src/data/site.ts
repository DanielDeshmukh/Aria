/* ------------------------------------------------------------------ */
/*  Aria — product display copy for the public site.                   */
/*  The implementation plan (deliverables, schedule, submission        */
/*  logistics, interview prep, matrix) stays frozen in ./plan.ts and   */
/*  is never rendered. Spec-truth data (policies, orders, A–E, test    */
/*  scenarios) is imported from plan.ts untouched; only product        */
/*  framing copy lives here.                                           */
/* ------------------------------------------------------------------ */

import {
  DECISIONS as PLAN_DECISIONS,
  DEPLOY_POINTS as PLAN_DEPLOY_POINTS,
  LENS as PLAN_LENS,
  NORMALIZATION as PLAN_NORMALIZATION,
  README_OUTLINE as PLAN_README_OUTLINE,
  REQUIREMENTS as PLAN_REQUIREMENTS,
  REPO_TREE as PLAN_REPO_TREE,
  RISKS as PLAN_RISKS,
  SECTION_9 as PLAN_SECTION_9,
  STACK as PLAN_STACK,
  type ReqGroup,
} from "./plan";

/* ---------------- navigation (ids stable, labels product-facing) ---------------- */

export const NAV = [
  { id: "lens", label: "Principles" },
  { id: "requirements", label: "Requirements" },
  { id: "data", label: "Knowledge" },
  { id: "architecture", label: "Architecture" },
  { id: "behaviour", label: "Behaviour" },
  { id: "tests", label: "Scenarios" },
  { id: "submission", label: "Walkthrough" },
  { id: "appendix", label: "Risks" },
];

/* ---------------- hero stats ---------------- */

export const HERO_STATS = [
  { value: 14, suffix: "", label: "voice scenarios", note: "full acceptance script" },
  { value: 6, suffix: "", label: "call states", note: "idle → ended, shown live" },
  { value: 0, suffix: "", label: "API keys in the browser", note: "every provider proxied server-side" },
  { value: 1.5, suffix: "s", decimals: 1, prefix: "<", label: "latency target", note: "end of speech → first audio" },
];

/* ---------------- 01 · principles ---------------- */

export const LENS = PLAN_LENS.map((l) =>
  l.n === "03"
    ? {
        ...l,
        desc: "Every part of the pipeline is explainable end to end — mic to speaker, where latency comes from, where each decision happens. No black boxes.",
      }
    : l.n === "04"
      ? {
          ...l,
          desc: "Shown in the docs — why this stack, what was hard, what changes at scale. Not through feature count.",
        }
      : l
);

/* ---------------- 02 · requirements (spec verbatim; framing strings patched) ---------------- */

export const REQUIREMENTS: ReqGroup[] = PLAN_REQUIREMENTS.map((g) => ({
  ...g,
  items: g.items.map((it) =>
    it.text.includes("evaluators never need the PDF")
      ? {
          ...it,
          text: "Test Orders Helper panel on the page — ORD-101/102/103 with full details, so anyone can test order lookups without external docs",
        }
      : it.text.includes("(my addition)")
        ? { ...it, text: "Live transcript during the call — makes testing and the walkthrough much clearer" }
        : it
  ),
}));

/* ---------------- architecture copy ---------------- */

export const STACK = PLAN_STACK.map((s) =>
  s.layer === "Frontend"
    ? { ...s, why: "Rich call UI with instant state feedback and a fast iteration loop." }
    : s.layer === "STT"
      ? {
          ...s,
          why: "Low latency, endpointing built in. Sarvam STT is the swap candidate if Hinglish or accent accuracy needs it.",
        }
      : s.layer === "Platform"
        ? {
            ...s,
            why: "Free tier, no card, Docker-native, WebSockets verified working, sleeps only after 48h idle.",
          }
        : s
);

export const DECISIONS = PLAN_DECISIONS.map((d) =>
  d.n === "01"
    ? {
        ...d,
        body: "Tools return computed facts — return_eligible: false, reason: “delivered 14 days ago; window is 7 days”. The LLM only phrases them. That split is how the guardrails actually hold.",
      }
    : d
);

export const DEPLOY_POINTS = PLAN_DEPLOY_POINTS.map((d) =>
  d.title === "Sleep & wake"
    ? {
        ...d,
        body: "Free Spaces sleep after 48h idle; waking takes 30–60s. Wake the Space before a demo window, and keep a free uptime pinger on it.",
      }
    : d.title === "Day-1 smoke test"
      ? { ...d, title: "First-deploy smoke test" }
      : d
);

/* ---------------- tools & behaviour ---------------- */

export const NORMALIZATION = {
  ...PLAN_NORMALIZATION,
  note: "Speech-to-text will garble “ORD-101” — “O R D one oh one”, “ord 101”, “or d 101”. Normalize in code, and add an STT keyterm hint if the provider supports it. This is the most likely thing to break in a live call.",
};

/* ---------------- design notes ---------------- */

export const REPO_TREE = PLAN_REPO_TREE.replace("aria-voice-agent/", "Aria/");

export const README_OUTLINE = PLAN_README_OUTLINE.map((r) =>
  r.includes("Notes for evaluators")
    ? "Notes for testers (use headphones, sample orders on the page)"
    : r.includes("Section-9 answers")
      ? "Design answers"
      : r
);

export const SECTION_9 = PLAN_SECTION_9.map((s) =>
  s.q.includes("most difficult")
    ? {
        ...s,
        a: "Latency plus speech-to-text mangling order IDs — solved with streaming, sentence-level TTS flush, and ID normalization; barge-in with echo is the runner-up.",
      }
    : s
);

/* ---------------- launch checklist ---------------- */

export const LAUNCH_CHECKLIST = [
  "Deployed URL tested on a different device and network; mic permission works",
  "HF Space is awake (no cold start) right before a test or demo",
  "All 14 voice scenarios pass on the deployed build",
  "Requirements A–E fully ticked",
  "Repo is public; no API keys in git history; .env.example complete",
  "README complete — setup, architecture, guardrails, design answers",
  "Walkthrough link opens without login (checked in incognito)",
  "API credits (Sarvam, Deepgram, Groq) healthy for several days of testing",
  "Test Orders Helper shows ORD-101/102/103 with full details",
  "Post-call transcript and JSON summary render after the call",
];

/* ---------------- risks ---------------- */

export const RISKS = PLAN_RISKS.map(([risk, fix]) =>
  risk.includes("HF Space sleeping")
    ? [risk, "Wake before demo windows; a free uptime pinger covers the rest"]
    : risk.includes("Outbound WebSocket")
      ? [risk, "First-deploy smoke test; Cloud Run as fallback"]
      : risk.includes("credits")
        ? ["API credits run out mid-test or mid-demo", "Check balances before a demo; add a friendly error if a provider fails"]
        : risk.includes("README and video")
          ? ["Docs drift late", "Start the README skeleton with the first commit"]
          : risk.includes("Over-building")
            ? [risk, "Finish A–E end-to-end first; extras are tiebreakers only"]
            : [risk, fix]
);
