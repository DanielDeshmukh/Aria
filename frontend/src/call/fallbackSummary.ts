import type { TranscriptEntry } from "./useVoiceSession";

/**
 * Client mirror of backend/summary.py::fallback_summary - used only when the
 * socket closes after a warned hosting-limit end before the server summary
 * arrives. Same 4-key shape and the SAME rule as the backend: the sentence is
 * rebuilt from structured facts (tool events, known order ids, keyword
 * intent) and NEVER quotes raw transcript lines ("Customer said: ...").
 *
 * Order-id normalizer is a deliberate pragmatic subset of the backend's:
 * digits, interior-O garble ("ORD1O1") and three-word spoken IDs
 * ("one oh one"), restricted to the known catalogue.
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

// Intent topic phrases for the no-tool-log fallback (backend _TOPIC).
const TOPIC: Record<string, string> = {
  ORDER_TRACKING: "order",
  CANCELLATION: "cancelling an order",
  RETURN_REFUND: "a return or refund",
  GENERAL_QUERY: "a product or policy question",
};

// The agent handing the call over: the escalation cue (backend _ESCALATION_RE).
const ESCALATION_RE =
  /\bescalat|\bhuman agent|speak to (a )?human|manager|supervisor|team will (contact|call|reach)|callback/i;

/** Structural subset of ToolEvent used here (args/result decide everything). */
export interface ToolEvidence {
  name: string;
  args?: Record<string, unknown>;
  result?: unknown;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : null;
}

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

/** A tool-supplied id counts only when the catalogue knows it (backend _known_order_id). */
function knownOrderId(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  return normalizeOrderId(String(value));
}

/** Authoritative order id: what the TOOLS were called with (and returned). */
function orderIdFromTools(tools: ReadonlyArray<ToolEvidence>): string | null {
  for (const entry of tools) {
    const args = asRecord(entry.args);
    const result = asRecord(entry.result);
    const fromArgs = knownOrderId(args?.order_id);
    if (fromArgs) return fromArgs;
    const fromResult =
      knownOrderId(result?.order_id) ?? knownOrderId(result?.requested);
    if (fromResult) return fromResult;
    const order = asRecord(result?.order);
    const fromOrder = knownOrderId(order?.id);
    if (fromOrder) return fromOrder;
  }
  return null;
}

/** Tool evidence beats keyword guessing (backend _intent_from_tools). */
function intentFromTools(
  tools: ReadonlyArray<ToolEvidence>,
  keywordIntent: string,
): string {
  for (const entry of tools) {
    if (entry.name === "cancel_order") return "CANCELLATION";
  }
  return keywordIntent;
}

/** Deterministic status rules, mirroring backend _resolution_status. */
function resolutionStatus(
  tools: ReadonlyArray<ToolEvidence>,
  agentLines: readonly string[],
  intent: string,
): string {
  for (const line of agentLines) {
    if (ESCALATION_RE.test(line)) return "ESCALATED";
  }
  if (agentLines.length === 0) return "UNRESOLVED";
  if (tools.length === 0) return "RESOLVED";
  const last = tools[tools.length - 1];
  const result = asRecord(last.result) ?? {};
  const error = result.error;
  if (last.name === "cancel_order") {
    if (result.cancelled === true) return "RESOLVED";
    if (error === "INELIGIBLE") return "RESOLVED"; // denial explained = answered
    return "UNRESOLVED"; // NOT_CONFIRMED / NOT_FOUND / no id
  }
  if (last.name === "get_order_details") {
    if (error === "NOT_FOUND" || error === "NO_ORDER_ID") return "UNRESOLVED";
    const flags = asRecord(result.flags) ?? {};
    if (intent === "RETURN_REFUND" && flags.return_eligible === false) {
      return "RESOLVED"; // explained denial
    }
    if (intent === "CANCELLATION" && flags.cancellable === false) {
      return "RESOLVED";
    }
    return "RESOLVED";
  }
  return "RESOLVED";
}

function subject(
  orderId: string | null,
  order: Record<string, unknown> | null,
): string {
  const product = order?.product;
  if (orderId && typeof product === "string" && product) {
    return `${orderId} (${product})`;
  }
  return orderId ?? "their order";
}

/**
 * Build call_summary from the decisive tool outcome - never from transcript
 * lines (backend _summary_from_tools). Returns null when there is nothing
 * tool-grounded to say.
 */
function summaryFromTools(
  tools: ReadonlyArray<ToolEvidence>,
  intent: string,
  orderId: string | null,
): string | null {
  if (tools.length === 0) return null;
  const last = tools[tools.length - 1];
  const args = asRecord(last.args) ?? {};
  const result = asRecord(last.result) ?? {};
  const order = asRecord(result.order);
  const oid = orderId ?? knownOrderId(args.order_id) ?? knownOrderId(result.order_id);
  const subj = subject(oid, order);

  if (last.name === "cancel_order") {
    if (result.cancelled === true) {
      return `Customer asked to cancel ${subj}. The order was cancelled.`;
    }
    if (result.error === "INELIGIBLE") {
      const reason = String(result.reason ?? "outside the cancellation policy");
      return `Customer asked to cancel ${subj}. Cancellation declined: ${reason}`;
    }
    if (result.error === "NOT_CONFIRMED") {
      return (
        `Customer asked to cancel ${subj}; confirmation was still ` +
        "pending when the call ended."
      );
    }
    if (result.error === "NO_ORDER_ID") {
      return "Customer asked to cancel an order without a readable id; a repeat of the id was still needed.";
    }
    return "Customer asked to cancel an order id that was not found; a readable id was still needed.";
  }

  if (last.name === "get_order_details") {
    if (result.found) {
      const status = typeof order?.status === "string" ? order.status : "";
      const flags = asRecord(result.flags) ?? {};
      if (intent === "RETURN_REFUND" && flags.return_eligible === false) {
        const reason = String(flags.return_reason ?? "outside the return window");
        return `Customer asked to return ${subj}. Return declined: ${reason}`;
      }
      if (intent === "CANCELLATION" && flags.cancellable === false) {
        const reason = String(flags.cancel_reason ?? "outside the cancellation policy");
        return `Customer asked to cancel ${subj}. Cancellation declined: ${reason}`;
      }
      if (status) return `Customer asked about ${subj}. Order status: ${status}.`;
      return `Customer asked about ${subj}.`;
    }
    if (result.error === "NO_ORDER_ID") {
      return "Customer asked about an order without a readable id; a repeat of the id was still needed.";
    }
    const requested = String(result.requested ?? oid ?? "an order id");
    return `Customer asked about ${requested}, which was not found; a readable id was still needed.`;
  }

  if (last.name === "get_policy_info") {
    const topic = String(result.topic ?? args.topic ?? "the applicable");
    return `Customer asked about ${topic} policy; the published policy was applied.`;
  }

  if (last.name === "end_call") {
    return "The customer had no further questions; Aria wrapped the call up.";
  }

  return null;
}

/**
 * Facts only, never transcript lines (backend _summary_from_facts). When no
 * keyword and no tool evidence pinned the intent down, use the fixed
 * unclear-intent sentence instead of guessing.
 */
function summaryFromFacts(
  intent: string,
  orderId: string | null,
  agentLines: readonly string[],
  keywordMatched: boolean,
): string {
  if (!keywordMatched) {
    return agentLines.length > 0
      ? "Customer contacted support; Aria responded and the call ended."
      : "Customer contacted support; no agent reply was recorded.";
  }
  let topic = TOPIC[intent] ?? "a product or policy question";
  if (orderId && intent === "ORDER_TRACKING") topic = `order ${orderId}`;
  else if (orderId && intent === "CANCELLATION") topic = `cancelling ${orderId}`;
  else if (orderId && intent === "RETURN_REFUND") topic = `returning ${orderId}`;
  if (agentLines.length === 0) {
    return `Customer asked about ${topic}; no agent reply was recorded.`;
  }
  return `Customer asked about ${topic}; Aria answered from the published policy.`;
}

export function clientFallbackSummary(
  transcript: TranscriptEntry[],
  tools: ReadonlyArray<ToolEvidence> = [],
): Record<string, unknown> {
  const customerLines = transcript
    .filter((t) => t.final && t.role === "customer" && t.text.trim())
    .map((t) => t.text);
  const agentLines = transcript
    .filter((t) => t.final && t.role === "agent" && t.text.trim())
    .map((t) => t.text);
  const haystack = customerLines.join(" ").toLowerCase();

  let intent = "GENERAL_QUERY";
  let keywordMatched = false;
  for (const [name, needles] of INTENT_RULES) {
    if (needles.some((n) => haystack.includes(n))) {
      intent = name;
      keywordMatched = true;
      break;
    }
  }
  intent = intentFromTools(tools, intent);

  // Known catalogue ids only (avoids "₹3,000" -> ORD-3000); tools first.
  let orderId: string | null = orderIdFromTools(tools);
  if (orderId === null) {
    for (const line of [...customerLines, ...agentLines]) {
      const found = normalizeOrderId(line);
      if (found) {
        orderId = found;
        break;
      }
    }
  }

  const status = resolutionStatus(tools, agentLines, intent);
  let callSummary: string =
    summaryFromTools(tools, intent, orderId) ??
    summaryFromFacts(intent, orderId, agentLines, keywordMatched);
  if (status === "ESCALATED" && !callSummary.toLowerCase().includes("escalat")) {
    callSummary = `${callSummary} The call was escalated to a human.`;
  }
  if (callSummary.length > 300) callSummary = callSummary.slice(0, 297) + "...";

  return {
    customer_intent: intent,
    order_id: orderId,
    resolution_status: status,
    call_summary: callSummary,
  };
}
