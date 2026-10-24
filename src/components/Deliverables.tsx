import { AtSign, FolderGit2, Globe, Mail, NotebookPen, Video } from "lucide-react";
import { DELIVERABLES, README_MUST } from "../data/plan";
import { Chip, Kicker, Reveal, Section, SectionHead } from "./ui";

const ICONS = [Globe, FolderGit2, Video, NotebookPen, AtSign, Mail];

export default function Deliverables() {
  return (
    <Section id="deliverables" className="py-24 md:py-32">
      <SectionHead
        no="03"
        kicker="100% non-negotiable"
        title={
          <>
            Six things
            <br />
            leave your hands
          </>
        }
        desc="Miss one and the build doesn't matter. Each has a strict definition of done."
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {DELIVERABLES.map((d, i) => {
          const Icon = ICONS[i];
          return (
            <Reveal key={d.n} delay={(i % 3) * 0.08}>
              <div className="group flex h-full flex-col rounded-2xl hairline bg-card p-6 transition-all duration-300 hover:-translate-y-1 hover:border-mint2 hover:shadow-[0_24px_45px_-30px_rgba(19,32,25,0.35)]">
                <div className="flex items-center justify-between">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-mint text-pined transition-colors duration-300 group-hover:bg-pine group-hover:text-white">
                    <Icon size={17} strokeWidth={2.1} />
                  </span>
                  <span className="font-mono text-[11px] text-ink2">0{d.n}</span>
                </div>
                <h3 className="mt-5 font-display text-xl font-medium tracking-tight text-ink">{d.title}</h3>
                <p className="mt-2 text-[13px] leading-relaxed text-ink2">{d.done}</p>
                <div className="mt-auto pt-5">
                  <span className="font-mono text-[10px] uppercase tracking-[0.24em] text-pine opacity-0 transition-opacity duration-300 group-hover:opacity-100">
                    done-when ↓ enforced
                  </span>
                </div>
              </div>
            </Reveal>
          );
        })}
      </div>

      <Reveal delay={0.1} className="mt-10">
        <div className="rounded-2xl bg-[#0f1c15] p-7 text-white md:p-9">
          <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
            <div className="max-w-md">
              <Kicker className="text-[#a5e8cd]">README must include · PDF section 9</Kicker>
              <p className="mt-3 font-display text-2xl font-medium leading-snug tracking-tight">
                The four questions<br />the README has to answer
              </p>
            </div>
            <ol className="grid flex-1 gap-2.5 sm:grid-cols-2 md:max-w-xl">
              {README_MUST.map((r, i) => (
                <li key={i} className="flex items-start gap-3 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3">
                  <span className="font-mono text-[11px] text-[#a5e8cd]">Q{i + 1}</span>
                  <span className="text-[13px] leading-relaxed text-white/85">{r}</span>
                </li>
              ))}
            </ol>
          </div>
          <div className="mt-6 flex flex-wrap items-center gap-2.5 border-t border-white/10 pt-5">
            <Chip tone="pine" className="border-transparent">full source code</Chip>
            <Chip tone="pine" className="border-transparent">.env.example</Chip>
            <Chip tone="pine" className="border-transparent">architecture + setup</Chip>
            <Chip tone="pop" className="border-transparent">no secrets committed</Chip>
          </div>
        </div>
      </Reveal>
    </Section>
  );
}
