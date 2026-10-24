import { motion } from "framer-motion";
import {
  AudioLines,
  AudioWaveform,
  BrainCircuit,
  FileJson,
  Mic,
  Server,
  ShieldCheck,
  Smartphone,
  Speaker,
  Split,
  Wrench,
} from "lucide-react";
import { HF_FRONTMATTER, SARVAM_NOTES } from "../data/plan";
import { DECISIONS, DEPLOY_POINTS, STACK } from "../data/site";
import { Chip, CodeBlock, Kicker, Reveal, Section, SectionHead } from "./ui";

/* travelling pulse along a connector */
function Pulse({ vertical = false, delay = 0, reverse = false, tone = "bg-pine" }: { vertical?: boolean; delay?: number; reverse?: boolean; tone?: string }) {
  const dist = 116;
  const x = reverse ? [dist, -4] : [-4, dist];
  const y = [-2, 26];
  return (
    <motion.span
      className={`absolute rounded-full ${tone}`}
      style={{ width: 7, height: 7, boxShadow: "0 0 0 3px rgba(11,122,91,0.15)" }}
      initial={{ opacity: 0 }}
      animate={
        vertical
          ? { top: 0, y, opacity: [0, 1, 1, 0] }
          : { left: 0, top: "50%", marginTop: -3.5, x, opacity: [0, 1, 1, 0] }
      }
      transition={{ duration: 1.7, repeat: Infinity, delay, ease: "linear", times: [0, 0.18, 0.82, 1] }}
    />
  );
}

function Node({
  icon: Icon,
  title,
  sub,
  className = "",
  accent = false,
}: {
  icon: typeof Mic;
  title: string;
  sub: string;
  className?: string;
  accent?: boolean;
}) {
  return (
    <div className={`flex items-center gap-3 rounded-xl border px-3.5 py-3 ${accent ? "border-mint2 bg-mint/50" : "border-line bg-card"} ${className}`}>
      <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${accent ? "bg-pine text-white" : "bg-paper text-pined"}`}>
        <Icon size={15} />
      </span>
      <span className="min-w-0">
        <span className="block truncate font-mono text-[11.5px] font-semibold text-ink">{title}</span>
        <span className="block truncate text-[10.5px] text-ink2">{sub}</span>
      </span>
    </div>
  );
}

function Diagram() {
  return (
    <div className="overflow-x-auto rounded-2xl hairline bg-card">
      <div className="min-w-[900px] p-6 md:p-9">
        {/* column headers */}
        <div className="grid grid-cols-[290px_140px_1fr] gap-0">
          <Kicker className="px-1">browser · react</Kicker>
          <Kicker className="text-center text-pine">websocket</Kicker>
          <Kicker className="px-4">fastapi — one deployable service</Kicker>
        </div>

        <div className="mt-3 grid grid-cols-[290px_140px_1fr]">
          {/* -------- browser cluster -------- */}
          <div className="flex flex-col justify-between gap-10 rounded-2xl bg-paper p-4">
            <div className="space-y-2">
              <Node icon={Mic} title="mic" sub="getUserMedia · echoCancellation: true" />
              <div className="flex justify-center py-0.5"><span className="h-4 w-px bg-mint2" /></div>
              <Node icon={AudioLines} title="AudioWorklet" sub="16 kHz PCM frames" accent />
            </div>
            <div className="rounded-xl border border-dashed border-line bg-card px-3.5 py-2.5 text-center">
              <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink2">ui state machine</span>
              <div className="mt-1 font-mono text-[10px] text-pine">idle → listening ⇄ thinking ⇄ speaking → ended</div>
            </div>
            <div className="space-y-2">
              <Node icon={AudioWaveform} title="WebAudio queue" sub="chunked playback · barge-in stop" />
              <div className="flex justify-center py-0.5"><span className="h-4 w-px bg-mint2" /></div>
              <Node icon={Speaker} title="speaker" sub="Indian-English voice, out loud" accent />
            </div>
          </div>

          {/* -------- WS lanes -------- */}
          <div className="relative flex flex-col justify-between py-10">
            <div className="relative px-3">
              <div className="flow-dash relative h-px w-full bg-transparent" style={{ borderTop: "2px dashed #9fc3ae" }} />
              <Pulse />
              <Pulse delay={0.85} />
              <span className="absolute -top-6 left-1/2 -translate-x-1/2 whitespace-nowrap font-mono text-[9.5px] uppercase tracking-[0.16em] text-pine">pcm up</span>
            </div>
            <div className="relative px-3">
              <div className="flow-dash relative h-px w-full" style={{ borderTop: "2px dashed #9fc3ae" }} />
              <Pulse reverse tone="bg-pop" delay={0.3} />
              <Pulse reverse tone="bg-pop" delay={1.15} />
              <span className="absolute -bottom-6 left-1/2 -translate-x-1/2 whitespace-nowrap font-mono text-[9.5px] uppercase tracking-[0.16em] text-pop">audio down</span>
            </div>
          </div>

          {/* -------- fastapi cluster -------- */}
          <div className="rounded-2xl border border-mint2 bg-mint/30 p-4">
            <div className="grid grid-cols-[230px_1fr] gap-3">
              {/* chain */}
              <div className="relative flex flex-col">
                <Node icon={AudioLines} title="Deepgram STT" sub="streaming · endpointing built-in" />
                <div className="relative ml-6 h-8 w-px" style={{ borderLeft: "2px dashed #9fc3ae" }}><Pulse vertical /></div>
                <Node icon={BrainCircuit} title="Groq · Llama 3.3 70B" sub="tool calling · Gemini Flash fallback" accent />
                <div className="relative ml-6 h-8 w-px" style={{ borderLeft: "2px dashed #9fc3ae" }}><Pulse vertical delay={0.4} /></div>
                <Node icon={Split} title="sentence splitter" sub="flush each sentence to TTS at once" />
                <div className="relative ml-6 h-8 w-px" style={{ borderLeft: "2px dashed #9fc3ae" }}><Pulse vertical delay={0.8} /></div>
                <Node icon={AudioWaveform} title="Sarvam bulbul:v4-flash" sub="WS TTS · sub-250ms first audio" accent />
              </div>

              {/* side systems */}
              <div className="flex flex-col justify-center gap-3">
                <div className="rounded-xl border border-line bg-card p-3.5">
                  <div className="flex items-center gap-2 font-mono text-[11px] font-semibold text-ink">
                    <Wrench size={13} className="text-pine" /> tools + policy engine
                  </div>
                  <p className="mt-1.5 text-[10.5px] leading-relaxed text-ink2">
                    Python. Computes eligibility in code; the LLM only phrases the result.
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <span className="rounded bg-paper px-1.5 py-0.5 font-mono text-[9.5px] text-pined">get_order_details</span>
                    <span className="rounded bg-paper px-1.5 py-0.5 font-mono text-[9.5px] text-pined">get_policy_info</span>
                    <span className="rounded bg-paper px-1.5 py-0.5 font-mono text-[9.5px] text-pined">end_call</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 pl-1 font-mono text-[9.5px] uppercase tracking-[0.16em] text-ink2">
                  <span className="h-px w-5 bg-line" /> after end_call
                </div>
                <div className="rounded-xl border border-line bg-card p-3.5">
                  <div className="flex items-center gap-2 font-mono text-[11px] font-semibold text-ink">
                    <FileJson size={13} className="text-pop" /> post-call summarizer
                  </div>
                  <p className="mt-1.5 text-[10.5px] leading-relaxed text-ink2">
                    Transcript + structured JSON outcome for every call.
                  </p>
                </div>
                <div className="rounded-xl border border-dashed border-line bg-card/60 p-3">
                  <div className="flex items-center gap-2 font-mono text-[10px] text-ink2">
                    <ShieldCheck size={13} className="text-pine" /> api keys live here — never in the browser
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* caption row */}
        <div className="mt-8 flex flex-wrap items-center gap-2 border-t border-line pt-5">
          <Chip tone="pop">target &lt; 1.5s, end of speech → first audio</Chip>
          <Chip tone="pine">single wss origin — no CORS</Chip>
          <Chip tone="pine">sentence-level streaming</Chip>
          <Chip tone="warm">greeting plays instantly on Start Call</Chip>
        </div>
      </div>
    </div>
  );
}

export default function Architecture() {
  return (
    <Section id="architecture" className="py-24 md:py-32">
      <SectionHead
        no="04"
        kicker="stack & pipeline"
        title={
          <>
            The machine,
            <br />
            drawn once
          </>
        }
        desc="A modular pipeline — every stage owned, observable and explainable. Slow where it can be, fast where it must be."
        right={<Server size={20} className="hidden text-ink2 md:block" />}
      />

      <Reveal>
        <Diagram />
      </Reveal>

      {/* stack table */}
      <Reveal delay={0.05} className="mt-10">
        <div className="overflow-hidden rounded-2xl hairline bg-card">
          <div className="border-b border-line px-6 py-4">
            <Kicker>stack decisions — layer → choice → why</Kicker>
          </div>
          <div className="divide-y divide-line/70">
            {STACK.map((s, i) => (
              <motion.div
                key={s.layer}
                initial={{ opacity: 0, x: -14 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, margin: "-40px" }}
                transition={{ delay: i * 0.05, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
                className="grid gap-1 px-6 py-4 transition-colors hover:bg-mint/25 md:grid-cols-[110px_300px_1fr] md:gap-4"
              >
                <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-pine">{s.layer}</span>
                <span className="text-[13.5px] font-semibold text-ink">{s.choice}</span>
                <span className="text-[13px] leading-relaxed text-ink2">{s.why}</span>
              </motion.div>
            ))}
          </div>
        </div>
      </Reveal>

      {/* key design decisions */}
      <div className="mt-14">
        <Reveal><Kicker>four key design decisions</Kicker></Reveal>
        <div className="mt-5 space-y-4">
          <Reveal>
            <div className="grid gap-0 overflow-hidden rounded-2xl hairline bg-[#0f1c15] text-white md:grid-cols-[220px_1fr]">
              <div className="flex items-center gap-4 bg-[#0a5c45] p-7">
                <span className="font-display text-6xl font-semibold text-white/25">01</span>
                <ShieldCheck size={26} className="text-[#c9e8d5]" />
              </div>
              <div className="p-7">
                <h3 className="font-display text-2xl font-medium tracking-tight">{DECISIONS[0].title}</h3>
                <p className="mt-2 max-w-2xl text-[13.5px] leading-relaxed text-white/70">{DECISIONS[0].body}</p>
                <div className="mt-4 inline-flex flex-wrap items-center gap-2 rounded-lg border border-white/15 bg-white/[0.05] px-3 py-2 font-mono text-[11px] text-[#c9e8d5]">
                  {"{ return_eligible: false, reason: \"delivered 14 days ago; window is 7 days\" }"}
                </div>
              </div>
            </div>
          </Reveal>
          <div className="grid gap-4 md:grid-cols-3">
            {DECISIONS.slice(1).map((d, i) => (
              <Reveal key={d.n} delay={i * 0.08}>
                <div className="h-full rounded-2xl hairline bg-card p-6 transition-all duration-300 hover:-translate-y-1 hover:border-mint2">
                  <span className="font-display text-3xl font-semibold text-mint2">{d.n}</span>
                  <h4 className="mt-3 font-display text-lg font-medium tracking-tight text-ink">{d.title}</h4>
                  <p className="mt-2 text-[13px] leading-relaxed text-ink2">{d.body}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </div>

      {/* sarvam notes + deployment */}
      <div className="mt-14 grid gap-4 lg:grid-cols-2">
        <Reveal>
          <div className="h-full rounded-2xl hairline bg-card p-7">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-mint text-pined">
                <AudioWaveform size={16} />
              </span>
              <h3 className="font-display text-xl font-medium tracking-tight">Sarvam Bulbul v4 Flash — field notes</h3>
            </div>
            <ul className="mt-5 space-y-2.5">
              {SARVAM_NOTES.map((n, i) => (
                <li key={i} className="flex items-start gap-2.5 text-[13px] leading-relaxed text-ink2">
                  <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-pine" />
                  <span>{n}</span>
                </li>
              ))}
            </ul>
          </div>
        </Reveal>
        <Reveal delay={0.08}>
          <div className="flex h-full flex-col gap-4">
            <div className="rounded-2xl hairline bg-card p-7">
              <div className="flex items-center gap-3">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-popsoft text-pop">
                  <Smartphone size={16} />
                </span>
                <h3 className="font-display text-xl font-medium tracking-tight">Deployment — Hugging Face Spaces (Docker)</h3>
              </div>
              <ul className="mt-5 space-y-3">
                {DEPLOY_POINTS.map((d, i) => (
                  <li key={i} className="flex items-start gap-3">
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-paper font-mono text-[10px] text-pined">{i + 1}</span>
                    <div>
                      <span className="block text-[13px] font-semibold text-ink">{d.title}</span>
                      <span className="block text-[12.5px] leading-relaxed text-ink2">{d.body}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Reveal>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <CodeBlock title="Space README.md front matter" code={HF_FRONTMATTER} />
        <CodeBlock
          title="dual remotes — GitHub is the public source, push to both"
          code={`git remote add hf https://huggingface.co/spaces/Daniel2503/<space-name>\n\n# secrets in Space Settings → Secrets:\nDEEPGRAM_API_KEY  GROQ_API_KEY  SARVAM_API_KEY`}
        />
      </div>
    </Section>
  );
}
