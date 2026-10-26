import type { TranscriptEntry } from "./useVoiceSession";

/**
 * Client mirror of backend/summary.py::fallback_summary — used only when the
 * socket closes after a warned hosting-limit end before the server summary
 * arrives. Same 4-key shape, keyword intent, known order IDs only (avoids
 * "₹3,000" -> ORD-3000). A deliberate pragmatic subset of the backend's full
 * spoken-ID normalizer: digits, interior-O garble ("ORD1O1") and
 * three-word spoken IDs ("one oh one").
 */

const KNOWN_ORDERS = ["ORD-101", "ORD-102", "ORD-103"];

const INTENT_RULES: ReadonlyArray<readonly [string, readonly string[]]> = [
  ["CANCELLATION", ["cancel", "cancell"]],
  ["RETURN_REFUND", ["return", "refund", "damaged", "broken", "defective"]],
  ["GENERAL_QUERY", ["cod", "shipping", "ingredient", "price", "discount"]],
  [
    "ORDER_TRACKING",
    ["order", "delivery", "delivered", "status", "where", "track", "kahan"],
  ],
];

const SPOKEN_DIGITS: Record<string, string> = {
  zero: "0",
  oh: "0",
  one: "1",
  two: "2",
  three: "3",
  four: "4",
  five: "5",
  six: "6",
  seven: "7",
  eight: "8",
  nine: "9",
};

function markKnown(digits: string): string | null {
  const id = `ORD-${digits}`;
  return KNOWN_ORDERS.includes(id) ? id : null;
}

function normalizeOrderId(line: string): string | null {
  const fixed = line.toLowerCase().replace(/(\d)o(?=\d)/g, "$10");
  const digits = /\bord(?:er)?[\s._-]*(\d{3,})/.exec(fixed);
  if (digits) return markKnown(digits[1]);
  const spoken = /\bord(?:er)?[\s._-]+([a-z]+(?:[\s-]+[a-z]+)+)/.exec(fixed);
  if (spoken) {
    const words = spoken[1].split(/[\s-]+/);
    if (words.length >= 3 && words.every((w) => w in SPOKEN_DIGITS)) {
      return markKnown(words.map((w) => SPOKEN_DIGITS[w]).join(""));
    }
  }
  return null;
}

export function clientFallbackSummary(
  transcript: TranscriptEntry[],
  tools: ReadonlyArray<{ name: string }> = [],
): Record<string, unknown> {
  const customerLines = transcript
    .filter((t) => t.final && t.role === "customer" && t.text.trim())
    .map((t) => t.text);
  const agentLines = transcript
    .filter((t) => t.final && t.role === "agent" && t.text.trim())
    .map((t) => t.text);
  const haystack = customerLines.join(" ").toLowerCase();

  let intent = "GENERAL_QUERY";
  for (const [name, needles] of INTENT_RULES) {
    if (needles.some((n) => haystack.includes(n))) {
      intent = name;
      break;
    }
  }
  // Tool events beat keyword guessing (mirrors backend _intent_from_tools).
  if (tools.some((t) => t.name === "cancel_order")) intent = "CANCELLATION";

  let orderId: string | null = null;
  for (const line of [...customerLines, ...agentLines]) {
    const found = normalizeOrderId(line);
    if (found) {
      orderId = found;
      break;
    }
  }

  const status = agentLines.length > 0 ? "RESOLVED" : "UNRESOLVED";
  const first = customerLines[0] ?? "the customer opened the call";
  const last = agentLines[agentLines.length - 1] ?? "no agent reply was recorded";
  let callSummary = `Customer said: ${first} Aria replied: ${last}`;
  if (callSummary.length > 300) callSummary = callSummary.slice(0, 297) + "...";

  return {
    customer_intent: intent,
    order_id: orderId,
    resolution_status: status,
    call_summary: callSummary,
  };
}
