interface QueueItem {
  buffer: AudioBuffer | null;
  failed: boolean;
}

function b64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function toLinear16Buffer(bytes: Uint8Array, mime: string): AudioBuffer | null {
  if (bytes.byteLength < 2) return null;
  const rateMatch = /rate=(\d+)/.exec(mime);
  const sampleRate = rateMatch ? Number(rateMatch[1]) : 16000;
  const pcm = new Int16Array(bytes.buffer, bytes.byteOffset, bytes.byteLength >> 1);
  const buffer = new AudioBuffer({ length: pcm.length, numberOfChannels: 1, sampleRate });
  const floats = new Float32Array(pcm.length);
  for (let i = 0; i < pcm.length; i++) floats[i] = pcm[i] / 32768;
  buffer.copyToChannel(floats, 0);
  return buffer;
}

class Playback {
  private ctx: AudioContext | null = null;
  private queue: QueueItem[] = [];
  private active = new Set<AudioBufferSourceNode>();
  private pending = 0;
  private nextTime = 0;
  private epoch = 0;
  private onDrain: (() => void) | null = null;

  private ensureContext(): AudioContext {
    if (!this.ctx) this.ctx = new AudioContext();
    if (this.ctx.state === "suspended") void this.ctx.resume();
    return this.ctx;
  }

  start(onDrain: () => void): void {
    this.onDrain = onDrain;
    this.ensureContext();
  }

  push(b64: string, mime: string): void {
    const ctx = this.ensureContext();
    const epoch = this.epoch;
    const item: QueueItem = { buffer: null, failed: false };
    this.queue.push(item);

    let bytes: Uint8Array<ArrayBuffer>;
    try {
      bytes = b64ToBytes(b64);
    } catch {
      item.failed = true;
      this.pump();
      return;
    }

    if (mime.startsWith("audio/l16")) {
      item.buffer = toLinear16Buffer(bytes, mime);
      if (!item.buffer) item.failed = true;
      this.pump();
      return;
    }

    this.pending += 1;
    ctx.decodeAudioData(bytes.buffer).then(
      (buffer) => {
        if (epoch !== this.epoch) return;
        item.buffer = buffer;
        this.pending -= 1;
        this.pump();
      },
      () => {
        if (epoch !== this.epoch) return;
        item.failed = true;
        this.pending -= 1;
        this.pump();
      },
    );
  }

  flush(): void {
    this.epoch += 1;
    this.queue = [];
    this.pending = 0;
    this.nextTime = 0;
    for (const source of this.active) {
      source.onended = null;
      try {
        source.stop();
      } catch {
        /* already stopped */
      }
      try {
        source.disconnect();
      } catch {
        /* already disconnected */
      }
    }
    this.active.clear();
    this.onDrain?.();
  }

  private pump(): void {
    const ctx = this.ctx;
    if (!ctx) return;
    while (this.queue.length > 0) {
      const head = this.queue[0];
      if (head.failed) {
        this.queue.shift();
        continue;
      }
      if (!head.buffer) return; // still decoding — keep arrival order
      const item = this.queue.shift();
      if (!item?.buffer) return;
      const source = ctx.createBufferSource();
      source.buffer = item.buffer;
      source.connect(ctx.destination);
      const when = Math.max(this.nextTime, ctx.currentTime);
      source.start(when);
      this.nextTime = when + item.buffer.duration;
      this.active.add(source);
      source.onended = () => {
        this.active.delete(source);
        this.pump();
      };
    }
    if (this.active.size === 0 && this.pending === 0 && this.queue.length === 0) {
      this.nextTime = 0;
      this.onDrain?.();
    }
  }
}

export const playback = new Playback();
