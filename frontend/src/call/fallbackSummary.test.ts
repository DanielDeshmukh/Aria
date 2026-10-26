import { describe, expect, it } from "vitest";
import { clientFallbackSummary } from "./fallbackSummary";
import type { ToolEvent, TranscriptEntry } from "./useVoiceSession";

/** Production bug: the old client fallback pasted transcript lines. */
const NEVER_QUOTE = /Customer said|Aria replied/;

function line(
  role: TranscriptEntry["role"],
  text: string,
  final = true,
): TranscriptEntry {
  return { role, text, final };
}

function tool(
  name: string,
  args: Record<string, unknown>,
  result: unknown,
): ToolEvent {
  return { name, args, result, at: 0 };
}

function summaryOf(
  transcript: TranscriptEntry[],
  tools: ToolEvent[] = [],
): Record<string, unknown> {
  const s = clientFallbackSummary(transcript, tools);
  expect(String(s.call_summary)).not.toMatch(NEVER_QUOTE);
  return s;
}

describe("clientFallbackSummary", () => {
  it("return denial grounded in the get_order_details tool result", () => {
    const s = summaryOf(
      [
        line("customer", "I want to return order ORD-102, the bottle arrived broken"),
        line("agent", "I checked - the return window has closed."),
      ],
      [
        tool(
          "get_order_details",
          { order_id: "ORD-102" },
          {
            found: true,
            order: {
              id: "ORD-102",
              status: "DELIVERED",
              product: "Vitamin C Serum",
            },
            flags: {
              return_eligible: false,
              return_reason: "outside the return window",
              cancellable: false,
            },
          },
        ),
      ],
    );
    expect(s.customer_intent).toBe("RETURN_REFUND");
    expect(s.order_id).toBe("ORD-102");
    expect(s.resolution_status).toBe("RESOLVED"); // denial explained = answered
    expect(s.call_summary).toBe(
      "Customer asked to return ORD-102 (Vitamin C Serum). Return declined: outside the return window",
    );
  });

  it("no tool call and unclear intent uses the fixed factual sentence", () => {
    const s = summaryOf([
      line("customer", "hello can you hear me"),
      line("agent", "Yes, hi - how can I help today?"),
    ]);
    expect(s.customer_intent).toBe("GENERAL_QUERY");
    expect(s.order_id).toBeNull();
    expect(s.resolution_status).toBe("RESOLVED");
    expect(s.call_summary).toBe(
      "Customer contacted support; Aria responded and the call ended.",
    );
  });

  it("tracking without tools is built from the intent keyword and known id", () => {
    const s = summaryOf([
      line("customer", "where is my order ORD-101"),
      line("agent", "It is out for delivery and arrives by 6 PM."),
    ]);
    expect(s.customer_intent).toBe("ORDER_TRACKING");
    expect(s.order_id).toBe("ORD-101");
    expect(s.resolution_status).toBe("RESOLVED");
    expect(s.call_summary).toBe(
      "Customer asked about order ORD-101; Aria answered from the published policy.",
    );
  });

  it("cancellation grounded in the cancel_order tool result", () => {
    const s = summaryOf(
      [
        line("customer", "please cancel my order"),
        line("agent", "Done - ORD-103 is cancelled."),
      ],
      [tool("cancel_order", { order_id: "ORD-103" }, { cancelled: true })],
    );
    expect(s.customer_intent).toBe("CANCELLATION");
    expect(s.order_id).toBe("ORD-103");
    expect(s.resolution_status).toBe("RESOLVED");
    expect(s.call_summary).toBe(
      "Customer asked to cancel ORD-103. The order was cancelled.",
    );
  });

  it("never quotes the transcript in any shape", () => {
    const s = summaryOf([
      line("customer", "my order ORD-102 is damaged and I want a refund"),
      line("agent", "I am sorry - I have noted the damage."),
      line("customer", "partial interim chatter", false), // non-final ignored
    ]);
    expect(String(s.call_summary)).not.toMatch(NEVER_QUOTE);
    expect(String(s.call_summary).length).toBeLessThanOrEqual(300);
  });
});
