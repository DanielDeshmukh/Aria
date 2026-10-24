import { AlertTriangle, Banknote, Leaf, RotateCcw, Truck, XCircle } from "lucide-react";
import { AMBIGUITY, BRAND_OVERVIEW, ORDERS, POLICIES } from "../data/plan";
import { Chip, Reveal, Section, SectionHead } from "./ui";

const POLICY_ICONS = [Truck, RotateCcw, XCircle, Banknote];

const STATUS_TONE: Record<string, "pine" | "warm" | "default"> = {
  "Out for Delivery": "warm",
  Delivered: "pine",
  Processing: "default",
};

export default function Policies() {
  return (
    <Section id="data" className="py-24 md:py-32">
      <SectionHead
        no="04"
        kicker="mock data & policies · from the PDF"
        title={
          <>
            The ground truth —
            <br />
            <span className="italic text-pine">do not alter</span>
          </>
        }
        desc="Policies and orders loaded exactly as given. Aria's knowledge begins and ends here; everything outside it is a polite “I don't have that information.”"
      />

      {/* brand overview */}
      <Reveal>
        <div className="flex flex-col items-start gap-4 rounded-2xl hairline bg-card p-6 sm:flex-row sm:items-center md:p-7">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-mint text-pined">
            <Leaf size={18} />
          </span>
          <div>
            <span className="font-mono text-[11px] uppercase tracking-[0.26em] text-ink2">brand overview — verbatim</span>
            <p className="mt-1 font-display text-xl font-light italic leading-snug text-ink md:text-2xl">
              “{BRAND_OVERVIEW}”
            </p>
          </div>
        </div>
      </Reveal>

      {/* policy cards */}
      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {POLICIES.map((p, i) => {
          const Icon = POLICY_ICONS[i];
          return (
            <Reveal key={p.id} delay={i * 0.07}>
              <div className="h-full rounded-2xl hairline bg-card p-6 transition-all duration-300 hover:-translate-y-1 hover:border-mint2">
                <div className="flex items-center gap-3">
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-paper text-pined">
                    <Icon size={16} />
                  </span>
                  <h3 className="font-display text-lg font-medium tracking-tight text-ink">{p.title}</h3>
                </div>
                <ul className="mt-4 space-y-2.5">
                  {p.rules.map((r, j) => (
                    <li key={j} className="flex items-start gap-2.5 text-[13px] leading-relaxed text-ink2">
                      <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-pine" />
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
            </Reveal>
          );
        })}
      </div>

      {/* ambiguity callout */}
      <Reveal delay={0.05} className="mt-8">
        <div className="relative overflow-hidden rounded-2xl border border-pop/40 bg-popsoft p-6 md:p-8">
          <span className="pointer-events-none absolute -bottom-8 -right-4 select-none font-display text-[9rem] font-semibold leading-none text-pop/10">
            ₹499
          </span>
          <div className="relative flex items-start gap-4">
            <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-pop text-white">
              <AlertTriangle size={17} />
            </span>
            <div>
              <h3 className="font-display text-xl font-medium tracking-tight text-ink">{AMBIGUITY.title}</h3>
              <p className="mt-2 max-w-3xl text-[13.5px] leading-relaxed text-ink/75">{AMBIGUITY.body}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Chip tone="pine">above ₹499 → free</Chip>
                <Chip tone="pop">below ₹499 → ₹50</Chip>
                <Chip tone="warm" className="border-pop/30 bg-card/60 text-pop">exactly ₹499 → honest “can't confirm”</Chip>
              </div>
            </div>
          </div>
        </div>
      </Reveal>

      {/* orders table */}
      <Reveal delay={0.05} className="mt-8">
        <div className="overflow-hidden rounded-2xl hairline bg-card">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-6 py-4">
            <div>
              <h3 className="font-display text-xl font-medium tracking-tight text-ink">Mock order database</h3>
              <p className="font-mono text-[11px] text-ink2">also ships as the on-page Test Orders Helper (Requirement E)</p>
            </div>
            <Chip tone="pine">3 orders · full details</Chip>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-left">
              <thead>
                <tr className="border-b border-line font-mono text-[10.5px] uppercase tracking-[0.18em] text-ink2">
                  <th className="px-6 py-3.5 font-medium">Order</th>
                  <th className="px-4 py-3.5 font-medium">Customer</th>
                  <th className="px-4 py-3.5 font-medium">Product</th>
                  <th className="px-4 py-3.5 font-medium">Value</th>
                  <th className="px-4 py-3.5 font-medium">Status</th>
                  <th className="px-6 py-3.5 font-medium">Details</th>
                </tr>
              </thead>
              <tbody>
                {ORDERS.map((o) => (
                  <tr key={o.id} className="group border-b border-line/70 transition-colors last:border-0 hover:bg-mint/25">
                    <td className="px-6 py-4">
                      <span className="rounded-md bg-[#0f1c15] px-2 py-1 font-mono text-[11.5px] font-medium text-[#c9e8d5]">{o.id}</span>
                    </td>
                    <td className="px-4 py-4 text-[13.5px] font-medium text-ink">{o.customer}</td>
                    <td className="px-4 py-4 text-[13.5px] text-ink2">{o.product}</td>
                    <td className="px-4 py-4 font-mono text-[13px] tabular text-ink">{o.value}</td>
                    <td className="px-4 py-4">
                      <Chip tone={STATUS_TONE[o.status]}>{o.status}</Chip>
                    </td>
                    <td className="px-6 py-4 text-[12.5px] leading-relaxed text-ink2">
                      {o.carrier !== "—" && (
                        <span className="font-mono">{o.carrier} · {o.tracking} — </span>
                      )}
                      {o.note}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Reveal>
    </Section>
  );
}
