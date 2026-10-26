import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { END_SUMMARY_WAIT_MS, useVoiceSession } from "./useVoiceSession";

const h = vi.hoisted(() => {
  class MockWebSocket {
    static readonly OPEN = 1;
    static readonly instances: MockWebSocket[] = [];
    readonly url: string;
    readyState = 1; // OPEN: handshake done, but the server NEVER sends a frame
    readonly sent: string[] = [];
    closeCalls = 0;
    onopen: ((ev: unknown) => void) | null = null;
    onmessage: ((ev: unknown) => void) | null = null;
    onclose: ((ev: unknown) => void) | null = null;
    onerror: ((ev: unknown) => void) | null = null;
    constructor(url: string) {
      this.url = url;
      MockWebSocket.instances.push(this);
    }
    send(data: string): void {
      this.sent.push(data); // fire-and-forget: no reply ever arrives
    }
    close(): void {
      this.closeCalls += 1;
      this.readyState = 3;
    }
  }
  const mic = {
    start: vi.fn(async () => undefined),
    stop: vi.fn(),
    error: null as string | null,
  };
  const playback = { start: vi.fn(), push: vi.fn(), flush: vi.fn() };
  return { MockWebSocket, mic, playback };
});

vi.mock("./useMic", () => ({ useMic: () => h.mic }));
vi.mock("./playback", () => ({ playback: h.playback }));

type MockWS = InstanceType<typeof h.MockWebSocket>;

function sentFrames(ws: MockWS): Record<string, unknown>[] {
  return ws.sent.map((s) => JSON.parse(s) as Record<string, unknown>);
}

async function startCall() {
  const view = renderHook(() => useVoiceSession());
  await act(async () => {
    await view.result.current.start();
  });
  const ws = h.MockWebSocket.instances[0];
  expect(ws).toBeDefined();
  return { view, ws };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  h.MockWebSocket.instances.length = 0;
  vi.stubGlobal("WebSocket", h.MockWebSocket);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("End Call ends locally on the click and falls back when the server never answers", async () => {
  const { view, ws } = await startCall();
  const { result } = view;

  // The user clicks End Call. The server stays completely silent.
  act(() => {
    result.current.end();
  });

  // Local close, synchronous with the click - zero server round trips:
  expect(h.mic.stop).toHaveBeenCalledTimes(1); // mic off
  expect(h.playback.flush).toHaveBeenCalledTimes(1); // playback off
  expect(result.current.state).toBe("ended"); // ended view rendered from local state
  expect(sentFrames(ws)).toEqual([{ type: "end" }]); // best-effort end frame sent
  // The socket is deliberately still open - ONLY as bounded grace for the
  // server summary; the UI never waits on it.
  expect(ws.closeCalls).toBe(0);

  // Repeated clicks (the production bug: 5+ dead clicks) are no-ops:
  act(() => {
    result.current.end();
    result.current.end();
  });
  expect(sentFrames(ws)).toHaveLength(1);
  expect(result.current.state).toBe("ended");

  // Server silent for the whole budget -> client-side fallback summary,
  // then the socket is closed locally. Nothing was ever received.
  act(() => {
    vi.advanceTimersByTime(END_SUMMARY_WAIT_MS - 1);
  });
  expect(result.current.summary).toBeNull();
  act(() => {
    vi.advanceTimersByTime(1);
  });
  expect(result.current.summary).not.toBeNull();
  expect(result.current.notice).toMatch(/prepared locally/);
  expect(ws.closeCalls).toBe(1);
});

it("a server summary arriving inside the wait window wins and cancels the fallback", async () => {
  const { view, ws } = await startCall();
  const { result } = view;
  act(() => {
    result.current.end();
  });

  const serverSummary = {
    customer_intent: "RETURN_REFUND",
    order_id: "ORD-102",
    resolution_status: "RESOLVED",
    call_summary: "server built this",
  };
  act(() => {
    ws.onmessage?.({
      data: JSON.stringify({ type: "summary", summary: serverSummary }),
    });
  });

  expect(result.current.summary).toEqual(serverSummary);
  expect(result.current.notice).toBeNull(); // no fallback note on the real summary
  expect(ws.closeCalls).toBe(1); // summary is terminal - socket freed at once

  // the fallback timer was cleared: waiting past it changes nothing
  act(() => {
    vi.advanceTimersByTime(END_SUMMARY_WAIT_MS * 2);
  });
  expect(result.current.summary).toEqual(serverSummary);
  expect(result.current.notice).toBeNull();
  expect(ws.closeCalls).toBe(1);
});
