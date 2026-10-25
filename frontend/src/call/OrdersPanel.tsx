import { useEffect, useRef, useState } from "react";
import { Chip } from "../components/ui";
import { ORDERS } from "../data/orders";
import { cn } from "../utils/cn";

const STATUS_TONE: Record<string, "default" | "pine" | "warm" | "pop"> = {
  "Out for Delivery": "warm",
  Delivered: "pine",
  Processing: "default",
};

export default function OrdersPanel() {
  const [copied, setCopied] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current);
    },
    [],
  );

  const copy = async (id: string) => {
    try {
      await navigator.clipboard.writeText(id);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = id;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    setCopied(id);
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setCopied(null), 1600);
  };

  return (
    <aside aria-label="test orders helper" className="rounded-2xl border border-line bg-card/70">
      <div className="border-b border-line px-4 py-3.5">
        <h2 className="font-display text-base font-medium text-ink">Test orders</h2>
        <p className="mt-1 text-[12.5px] leading-relaxed text-ink2">
          Speak an order id like <em className="font-mono font-semibold text-pine">ORD-101</em>{" "}
          during the call.
        </p>
      </div>
      <div className="max-h-[420px] space-y-2.5 overflow-y-auto p-3.5">
        {ORDERS.map((order) => (
          <div
            key={order.id}
            className="rounded-xl border border-line bg-card px-3.5 py-3 transition-colors duration-300 hover:border-mint2"
          >
            <div className="flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => copy(order.id)}
                title="Copy order id"
                className="group flex items-center gap-2 font-mono text-[12.5px] font-semibold text-pine transition-colors hover:text-pined"
              >
                {order.id}
                <span
                  className={cn(
                    "font-mono text-[10px] uppercase tracking-[0.18em] transition-opacity",
                    copied === order.id
                      ? "text-pine opacity-100"
                      : "text-ink2 opacity-0 group-hover:opacity-70",
                  )}
                >
                  {copied === order.id ? "copied" : "copy"}
                </span>
              </button>
              <Chip tone={STATUS_TONE[order.status] ?? "default"}>{order.status}</Chip>
            </div>
            <div className="mt-2.5 space-y-1">
              <p className="text-[13.5px] font-medium leading-snug text-ink">{order.product}</p>
              <p className="text-[12.5px] text-ink2">
                {order.customer} · <span className="font-semibold text-ink">{order.value}</span>
              </p>
              <p className="font-mono text-[11px] text-ink2">
                carrier: {order.carrier} · tracking: {order.tracking}
              </p>
              <p className="text-[12px] leading-relaxed text-ink2">{order.note}</p>
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}
