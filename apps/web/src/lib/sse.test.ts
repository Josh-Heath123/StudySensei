import { createSseParser, readSse, type SseEvent } from "./sse";

function parseAll(...chunks: string[]): SseEvent[] {
  const parser = createSseParser();
  return [...chunks.flatMap((chunk) => parser.push(chunk)), ...parser.end()];
}

function streamOf(...chunks: (string | Uint8Array)[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk);
      }
      controller.close();
    },
  });
}

describe("createSseParser", () => {
  test("names, data and ids, dispatched at a blank line", () => {
    expect(parseAll('event: delta\ndata: {"text":"Hi"}\n\nid: 7\ndata: plain\n\n')).toEqual([
      { event: "delta", data: '{"text":"Hi"}', id: undefined },
      { event: "message", data: "plain", id: "7" },
    ]);
  });

  test("multi-line data joins with newlines; comments and unknown fields are skipped", () => {
    expect(parseAll(": keep-alive\n\nretry: 10\nfoo: bar\ndata: a\ndata:b\ndata\n\n")).toEqual([
      { event: "message", data: "a\nb\n", id: undefined },
    ]);
  });

  test("\\r\\n and \\r end lines too, even split across chunks", () => {
    expect(parseAll("event: done\r", "\ndata: x\r\r", "data: y\r\n\r\n")).toEqual([
      { event: "done", data: "x", id: undefined },
      { event: "message", data: "y", id: undefined },
    ]);
  });

  test("an event split anywhere arrives once, whole", () => {
    const text = 'event: delta\ndata: {"text":"one"}\n\nevent: delta\ndata: {"text":"two"}\n\n';
    for (let cut = 1; cut < text.length; cut++) {
      expect(parseAll(text.slice(0, cut), text.slice(cut)).map((e) => e.data)).toEqual([
        '{"text":"one"}',
        '{"text":"two"}',
      ]);
    }
  });

  test("an event cut off by the end of the stream is dropped", () => {
    expect(parseAll("data: whole\n\ndata: half")).toEqual([
      { event: "message", data: "whole", id: undefined },
    ]);
  });

  test("an event with no data line isn't dispatched", () => {
    expect(parseAll("event: ping\n\n")).toEqual([]);
  });
});

describe("readSse", () => {
  test("reads a body as it streams, with multi-byte characters split between chunks", async () => {
    const bytes = new TextEncoder().encode("data: 【S1】\n\n");
    const events: SseEvent[] = [];
    for await (const event of readSse(streamOf(bytes.slice(0, 8), bytes.slice(8)))) {
      events.push(event);
    }
    expect(events).toEqual([{ event: "message", data: "【S1】", id: undefined }]);
  });
});
