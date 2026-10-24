import { useCallback, useRef, useState } from "react";

export type MicFrameHandler = (b64: string) => void;

export interface MicApi {
  start: (onFrame: MicFrameHandler) => Promise<void>;
  stop: () => void;
  error: string | null;
}

const DENIED_MESSAGE = "Microphone access was denied — allow the mic and retry.";
const NO_MIC_MESSAGE = "No microphone found.";
const UNAVAILABLE_MESSAGE = "Microphone unavailable.";

function toBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}

export function useMic(): MicApi {
  const [error, setError] = useState<string | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const moduleLoadedRef = useRef(false);
  const nodeRef = useRef<AudioWorkletNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const stop = useCallback(() => {
    sourceRef.current?.disconnect();
    sourceRef.current = null;
    nodeRef.current?.port.close();
    nodeRef.current?.disconnect();
    nodeRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    void contextRef.current?.suspend();
  }, []);

  const start = useCallback(
    async (onFrame: MicFrameHandler) => {
      setError(null);
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });
        streamRef.current = stream;

        const context = contextRef.current ?? new AudioContext();
        contextRef.current = context;
        await context.resume();
        if (!moduleLoadedRef.current) {
          await context.audioWorklet.addModule("/pcm-worklet.js");
          moduleLoadedRef.current = true;
        }

        const node = new AudioWorkletNode(context, "pcm-capture");
        node.port.onmessage = (event: MessageEvent<{ pcm: ArrayBuffer }>) => {
          onFrame(toBase64(event.data.pcm));
        };
        nodeRef.current = node;

        const source = context.createMediaStreamSource(stream);
        sourceRef.current = source;
        source.connect(node);
      } catch (err) {
        stop();
        const name = err instanceof DOMException ? err.name : "";
        const message =
          name === "NotAllowedError" || name === "SecurityError"
            ? DENIED_MESSAGE
            : name === "NotFoundError"
              ? NO_MIC_MESSAGE
              : UNAVAILABLE_MESSAGE;
        setError(message);
        throw new Error(message);
      }
    },
    [stop],
  );

  return { start, stop, error };
}
