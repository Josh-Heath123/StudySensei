/**
 * Server-sent events, read from a fetch body (WHATWG "event stream interpretation").
 *
 * `EventSource` can only GET, and the tutor POSTs its question, so the stream is read by
 * hand: lines end in \n, \r\n or \r; `data:` lines join with \n; `event:` names the event
 * ("message" by default); a blank line dispatches it; comments (`:`) and unknown fields
 * are ignored; an event cut off by the end of the stream is dropped.
 */

export type SseEvent = { event: string; data: string; id?: string };

/** An incremental parser: push text as it arrives, get back each event once complete. */
export function createSseParser() {
  let buffer = "";
  let data: string[] = [];
  let event = "";
  let id: string | undefined;
  let sawData = false;

  function line(text: string, out: SseEvent[]) {
    if (text === "") {
      if (sawData) out.push({ event: event || "message", data: data.join("\n"), id });
      data = [];
      event = "";
      sawData = false;
      return;
    }
    if (text.startsWith(":")) return;
    const colon = text.indexOf(":");
    const field = colon === -1 ? text : text.slice(0, colon);
    let value = colon === -1 ? "" : text.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "data") {
      data.push(value);
      sawData = true;
    } else if (field === "event") {
      event = value;
    } else if (field === "id" && !value.includes("\0")) {
      id = value;
    }
  }

  return {
    push(chunk: string): SseEvent[] {
      buffer += chunk;
      const out: SseEvent[] = [];
      for (;;) {
        const match = /\r\n|\r|\n/.exec(buffer);
        // A lone \r at the end may be the first half of \r\n: wait for more.
        if (!match || (match[0] === "\r" && match.index === buffer.length - 1)) break;
        line(buffer.slice(0, match.index), out);
        buffer = buffer.slice(match.index + match[0].length);
      }
      return out;
    },
    /** The stream ended: a trailing lone \r still ends its line; a half event is dropped. */
    end(): SseEvent[] {
      const out: SseEvent[] = [];
      if (buffer.endsWith("\r")) line(buffer.slice(0, -1), out);
      buffer = "";
      return out;
    },
  };
}

/** Every event of a response body, in order, as it streams in. */
export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseEvent> {
  const parser = createSseParser();
  const decoder = new TextDecoder();
  const reader = body.getReader();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      yield* parser.push(decoder.decode(value, { stream: true }));
    }
    yield* parser.push(decoder.decode());
    yield* parser.end();
  } finally {
    reader.releaseLock();
  }
}
