/* ------------------------------------------------------------------ */
/*  Aria — product display copy for the public site.                   */
/*  Spec-truth data (policies, orders, scenarios, the full master      */
/*  plan) stays frozen in ./plan.ts and is no longer rendered;         */
/*  only product framing copy lives here.                              */
/* ------------------------------------------------------------------ */

/* ---------------- navigation (landing sections in page order, ids = clean paths) ---------------- */

export const NAV = [
  { id: "call", label: "Live call" },
  { id: "pipeline", label: "How it works" },
];

/* ---------------- hero stats ---------------- */

export const HERO_STATS = [
  { value: 14, suffix: "", label: "voice scenarios", note: "full acceptance script" },
  { value: 6, suffix: "", label: "call states", note: "idle → ended, shown live" },
  { value: 0, suffix: "", label: "API keys in the browser", note: "every provider proxied server-side" },
  { value: 2, suffix: "s", decimals: 0, prefix: "~", label: "reply latency", note: "end of speech → first audio" },
];

/* ---------------- pipeline steps (landing "how it works") ---------------- */

export const PIPELINE = [
  {
    n: "01",
    title: "Capture",
    desc: "An AudioWorklet grabs the mic, downsamples to 16 kHz PCM16 and streams 100 ms frames over one WebSocket. Raw audio never touches a third party — only this server sees the frames.",
  },
  {
    n: "02",
    title: "Listen",
    desc: "Deepgram nova-3 streams speech-to-text with the language set in one config value (a final in any other script is caught and asked to repeat), endpointing at 800 ms, and every interim doubles as a barge-in signal while Aria is speaking.",
  },
  {
    n: "03",
    title: "Reason",
    desc: "Groq answers with tool calls; the tools compute their verdicts from policy.py and orders.json. The model phrases the decision — code makes it, so guardrails hold under pressure.",
  },
  {
    n: "04",
    title: "Speak",
    desc: "Sarvam Bulbul v4 Flash synthesizes sentence by sentence and streams each sentence's audio chunk by chunk, so the first audio reaches the speaker in about two seconds instead of waiting for the whole reply to finish.",
  },
];

export const PIPELINE_QUOTE =
  "One WebSocket connection, four stages, about two seconds from the end of speech to a voice that answers.";
