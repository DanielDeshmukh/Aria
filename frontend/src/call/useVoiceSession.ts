import { useCallback, useEffect, useReducer, useRef } from "react";
import { clientFallbackSummary } from "./fallbackSummary";
import { playback } from "./playback";
import { useMic } from "./useMic";

export type CallState =
  | "idle"
  | "connecting"
  | "listening"
  | "thinking"
  | "speaking"
  | "ended"
  | "error";

export type TranscriptRole = "customer" | "agent";

export interface TranscriptEntry {
  role: TranscriptRole;
  text: string;
  final: boolean;
}

export interface ToolEvent {
  name: string;
  args: Record<string, unknown>;
  result: unknown;
  /** transcript length when the tool fired — keeps the live log in order */
  at: number;
}

export interface CallStats {
  first_audio_ms: number;
  /** server-side order lookup + policy verdict, ms (tool turns only) */
  tool_lookup_ms?: number;
}

export type CallSummary = Record<string, unknown>;

export interface SessionData {
  state: CallState;
  transcript: TranscriptEntry[];
  tools: ToolEvent[];
  stats: CallStats | null;
  summary: CallSummary | null;
  error: string | null;
  notice: string | null;
}

const INITIAL: SessionData = {
  state: "idle",
  transcript: [],
  tools: [],
  stats: null,
  summary: null,
  error: null,
  notice: null,
};

/** After a local End Call the socket may linger this long ONLY to receive
 * the server summary, then the client-side fallback takes over. The local
 * close itself is synchronous with the click (mic, playback, ended view) and
 * never waits for a server message. Backend budget is
 * SUMMARY_TIMEOUT_SECONDS = 6 s (STT close runs concurrently with it), so
 * 6.5 s = server budget + delivery margin - a late server summary still
 * wins over the fallback. */
export const END_SUMMARY_WAIT_MS = 6500;
/** Shown whenever the summary was built locally instead of by the server. */
const LOCAL_SUMMARY_NOTE =
  "Summary prepared locally from the call transcript — the server summary did not arrive in time.";
/** "The agent wrapped the call up": a close after this is a normal end, not a
 * mid-call connection failure. */
const FAREWELL_RE = /thank you for reaching out|have a great day/i;

type Action =
  | { type: "state"; state: CallState }
  | { type: "transcript"; role: TranscriptRole; text: string; final: boolean }
  | { type: "tool"; event: Omit<ToolEvent, "at"> }
  | { type: "stats"; stats: CallStats }
  | { type: "summary"; summary: CallSummary }
  | { type: "error"; error: string }
  | { type: "notice"; notice: string }
  | { type: "reset" };

function reducer(state: SessionData, action: Action): SessionData {
  switch (action.type) {
    case "reset":
      return { ...INITIAL };
    case "state":
      // a client-side error wins over late provider state events (Retry stays)
      if (state.state === "error") return state;
      return { ...state, state: action.state };
    case "transcript": {
      const list = [...state.transcript];
      if (action.final) {
        for (let i = list.length - 1; i >= 0; i--) {
          const entry = list[i];
          if (entry.role !== action.role) continue;
          if (!entry.final) {
            list[i] = { role: action.role, text: action.text, final: true };
            return { ...state, transcript: list };
          }
          break; // same role's latest entry already final — append below
        }
        list.push({ role: action.role, text: action.text, final: true });
        return { ...state, transcript: list };
      }
      const last = list[list.length - 1];
      if (last && last.role === action.role && !last.final) {
        list[list.length - 1] = { ...last, text: action.text };
        return { ...state, transcript: list };
      }
      list.push({ role: action.role, text: action.text, final: false });
      return { ...state, transcript: list };
    }
    case "tool":
      return {
        ...state,
        tools: [...state.tools, { ...action.event, at: state.transcript.length }],
      };
    case "stats":
      return { ...state, stats: action.stats };
    case "summary":
      return { ...state, summary: action.summary, state: "ended" };
    case "error":
      return { ...state, error: action.error, state: "error" };
    case "notice":
      return { ...state, notice: action.notice };
  }
}

export function useVoiceSession() {
  const [data, dispatch] = useReducer(reducer, INITIAL);
  const mic = useMic();
  const wsRef = useRef<WebSocket | null>(null);
  const stateRef = useRef<CallState>("idle");
  stateRef.current = data.state;
  const transcriptRef = useRef<TranscriptEntry[]>([]);
  transcriptRef.current = data.transcript;
  const toolsRef = useRef<ToolEvent[]>([]);
  toolsRef.current = data.tools;
  const summaryRef = useRef<CallSummary | null>(null);
  summaryRef.current = data.summary;
  const endingSoonRef = useRef(false);
  // The call has effectively ended: end_call tool seen, farewell spoken, or
  // the user clicked End Call. A socket close after this must never show
  // "Connection lost".
  const endCallSeenRef = useRef(false);
  const farewellRef = useRef(false);
  const localEndRef = useRef(false);
  const endWaitRef = useRef<number | null>(null);

  const clearEndWait = useCallback(() => {
    if (endWaitRef.current !== null) {
      window.clearTimeout(endWaitRef.current);
      endWaitRef.current = null;
    }
  }, []);

  const sendJson = useCallback((payload: Record<string, unknown>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload));
  }, []);

  const sendAudio = useCallback((b64: string) => sendJson({ type: "audio", data: b64 }), [sendJson]);
  const playbackDone = useCallback(() => sendJson({ type: "playback_done" }), [sendJson]);

  const teardownSocket = useCallback(() => {
    const ws = wsRef.current;
    if (!ws) return;
    ws.onmessage = null;
    ws.onclose = null;
    ws.onerror = null;
    try {
      ws.close();
    } catch {
      /* already closed */
    }
    wsRef.current = null;
  }, []);

  // The socket closed (or the local summary wait elapsed) after the call had
  // effectively ended: end with the server summary if we have one, otherwise
  // build the client-side fallback from the transcript + tool events and add
  // a small note - never the red "Connection lost" banner.
  const finishLocally = useCallback(() => {
    const existing = summaryRef.current;
    if (existing) {
      dispatch({ type: "summary", summary: existing });
      clearEndWait();
      teardownSocket();
      return;
    }
    dispatch({
      type: "summary",
      summary: clientFallbackSummary(transcriptRef.current, toolsRef.current),
    });
    dispatch({ type: "notice", notice: LOCAL_SUMMARY_NOTE });
    clearEndWait();
    teardownSocket();
  }, [clearEndWait, teardownSocket]);

  const callEffectivelyEnded = useCallback(
    () =>
      localEndRef.current ||
      endCallSeenRef.current ||
      farewellRef.current ||
      stateRef.current === "ended",
    [],
  );

  const start = useCallback(async () => {
    dispatch({ type: "reset" });
    teardownSocket();
    clearEndWait();
    endingSoonRef.current = false;
    endCallSeenRef.current = false;
    farewellRef.current = false;
    localEndRef.current = false;
    // show connecting immediately: badge truth + onclose treats unclean
    // drops during handshake as connection-lost instead of silent idle
    dispatch({ type: "state", state: "connecting" });
    try {
      await mic.start(sendAudio);
    } catch (err) {
      dispatch({
        type: "error",
        error: err instanceof Error && err.message ? err.message : "Microphone unavailable.",
      });
      return;
    }
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/call`);
    wsRef.current = ws;
    playback.start(playbackDone);

    ws.onopen = () => sendJson({ type: "start" });
    ws.onmessage = (event) => {
      let msg: Record<string, unknown>;
      try {
        msg = JSON.parse(String(event.data)) as Record<string, unknown>;
      } catch {
        return;
      }
      switch (msg.type) {
        case "state": {
          const next = msg.state;
          if (typeof next === "string") dispatch({ type: "state", state: next as CallState });
          if (next === "ended") mic.stop();
          break;
        }
        case "transcript": {
          const role = msg.role;
          if (role !== "customer" && role !== "agent") break;
          const text = typeof msg.text === "string" ? msg.text : "";
          if (!text.trim()) break; // blank interim/final — no empty rows
          if (role === "agent" && msg.final === true && FAREWELL_RE.test(text)) {
            farewellRef.current = true; // a close after this is a normal end
          }
          dispatch({ type: "transcript", role, text, final: msg.final === true });
          break;
        }
        case "audio":
          if (typeof msg.data === "string") {
            playback.push(msg.data, typeof msg.mime === "string" ? msg.mime : "");
          }
          break;
        case "barge_in":
          playback.flush();
          break;
        case "tool":
          if (msg.name === "end_call") {
            endCallSeenRef.current = true; // agent-initiated end
          }
          dispatch({
            type: "tool",
            event: {
              name: String(msg.name ?? ""),
              args: (msg.args as Record<string, unknown> | null) ?? {},
              result: msg.result ?? null,
            },
          });
          break;
        case "stats":
          if (typeof msg.first_audio_ms === "number") {
            dispatch({
              type: "stats",
              stats: {
                first_audio_ms: msg.first_audio_ms,
                ...(typeof msg.tool_lookup_ms === "number"
                  ? { tool_lookup_ms: msg.tool_lookup_ms }
                  : {}),
              },
            });
          }
          break;
        case "summary":
          clearEndWait(); // the server summary won the race
          if (msg.summary && typeof msg.summary === "object") {
            dispatch({ type: "summary", summary: msg.summary as CallSummary });
          }
          mic.stop();
          teardownSocket(); // summary is the terminal event — free the socket
          break;
        case "call_ending_soon": {
          endingSoonRef.current = true;
          const left =
            typeof msg.seconds_left === "number"
              ? Math.max(1, Math.round(msg.seconds_left))
              : 30;
          dispatch({
            type: "notice",
            notice: `This call will automatically end in about ${left} seconds (hosting time limit).`,
          });
          break;
        }
        case "error":
          playback.flush();
          mic.stop();
          dispatch({
            type: "error",
            error: typeof msg.message === "string" && msg.message ? msg.message : "Call failed.",
          });
          break;
      }
    };
    ws.onclose = () => {
      if (wsRef.current !== ws) return;
      wsRef.current = null;
      const current = stateRef.current;
      // Already finished locally (End Call / summary / error): a close here
      // is expected - the summary wait (if still pending) resolves itself.
      if (current === "ended" || current === "idle" || current === "error") return;
      if (
        current === "connecting" ||
        current === "listening" ||
        current === "thinking" ||
        current === "speaking"
      ) {
        mic.stop();
        playback.flush();
        if (endingSoonRef.current || callEffectivelyEnded()) {
          // Warned time-limit drop OR the call had effectively ended
          // (end_call tool / farewell / local End Call): end with the
          // transcript + summary - never "Connection lost".
          finishLocally();
          return;
        }
        dispatch({ type: "error", error: "Connection lost — please retry." });
      }
    };
  }, [callEffectivelyEnded, clearEndWait, finishLocally, mic, playbackDone, sendAudio, sendJson, teardownSocket]);

  const end = useCallback(() => {
    if (localEndRef.current) return; // idempotent: the first click wins
    localEndRef.current = true;
    sendJson({ type: "end" }); // best-effort - never depend on the server
    mic.stop(); // stop capture instantly, whatever the server is doing
    playback.flush(); // stop audio instantly (re-sync playback_done is moot)
    if (stateRef.current !== "ended" && stateRef.current !== "error") {
      dispatch({ type: "state", state: "ended" }); // instant ended view
    }
    if (summaryRef.current) {
      teardownSocket();
      return;
    }
    // Give the server its full worst-case budget; then fall back locally.
    clearEndWait();
    endWaitRef.current = window.setTimeout(() => {
      endWaitRef.current = null;
      finishLocally();
    }, END_SUMMARY_WAIT_MS);
  }, [clearEndWait, finishLocally, mic, sendJson, teardownSocket]);

  const retry = useCallback(async () => {
    playback.flush();
    mic.stop();
    teardownSocket();
    await start();
  }, [mic, start, teardownSocket]);

  useEffect(
    () => () => {
      clearEndWait();
      teardownSocket();
      mic.stop();
      playback.flush();
    },
    [clearEndWait, mic.stop, teardownSocket],
  );

  return {
    state: data.state,
    transcript: data.transcript,
    tools: data.tools,
    stats: data.stats,
    summary: data.summary,
    notice: data.notice,
    error: data.error ?? mic.error,
    start,
    end,
    sendAudio,
    playbackDone,
    retry,
  };
}
