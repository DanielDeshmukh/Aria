import { useCallback, useEffect, useReducer, useRef } from "react";
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
}

export type CallSummary = Record<string, unknown>;

export interface SessionData {
  state: CallState;
  transcript: TranscriptEntry[];
  tools: ToolEvent[];
  stats: CallStats | null;
  summary: CallSummary | null;
  error: string | null;
}

const INITIAL: SessionData = {
  state: "idle",
  transcript: [],
  tools: [],
  stats: null,
  summary: null,
  error: null,
};

type Action =
  | { type: "state"; state: CallState }
  | { type: "transcript"; role: TranscriptRole; text: string; final: boolean }
  | { type: "tool"; event: Omit<ToolEvent, "at"> }
  | { type: "stats"; stats: CallStats }
  | { type: "summary"; summary: CallSummary }
  | { type: "error"; error: string }
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
  }
}

export function useVoiceSession() {
  const [data, dispatch] = useReducer(reducer, INITIAL);
  const mic = useMic();
  const wsRef = useRef<WebSocket | null>(null);
  const stateRef = useRef<CallState>("idle");
  stateRef.current = data.state;

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

  const start = useCallback(async () => {
    dispatch({ type: "reset" });
    teardownSocket();
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
            dispatch({ type: "stats", stats: { first_audio_ms: msg.first_audio_ms } });
          }
          break;
        case "summary":
          if (msg.summary && typeof msg.summary === "object") {
            dispatch({ type: "summary", summary: msg.summary as CallSummary });
          }
          mic.stop();
          break;
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
      if (
        current === "connecting" ||
        current === "listening" ||
        current === "thinking" ||
        current === "speaking"
      ) {
        mic.stop();
        playback.flush();
        dispatch({ type: "error", error: "Connection lost — please retry." });
      }
    };
  }, [mic, playbackDone, sendAudio, sendJson, teardownSocket]);

  const end = useCallback(() => {
    sendJson({ type: "end" });
    playback.flush(); // stop queued audio now; the re-sync playback_done is ignored post-end
  }, [sendJson]);

  const retry = useCallback(async () => {
    playback.flush();
    mic.stop();
    teardownSocket();
    await start();
  }, [mic, start, teardownSocket]);

  useEffect(
    () => () => {
      teardownSocket();
      mic.stop();
      playback.flush();
    },
    [mic.stop, teardownSocket],
  );

  return {
    state: data.state,
    transcript: data.transcript,
    tools: data.tools,
    stats: data.stats,
    summary: data.summary,
    error: data.error ?? mic.error,
    start,
    end,
    sendAudio,
    playbackDone,
    retry,
  };
}
