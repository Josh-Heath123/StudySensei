import { citedLabels, splitCitations } from "./citations";
import {
  answeredBy,
  errorMessage,
  liveSources,
  modelName,
  spokenSentences,
  turnsFromMessages,
} from "./turns";
import type { StoredMessage } from "./api";

describe("splitCitations", () => {
  test("ASCII and full-width brackets, single and grouped labels", () => {
    expect(
      splitCitations("Tracks state [S1]. Ports【S2】【S4】 and [S3, S5]; [ S6 ; S7 ]."),
    ).toEqual([
      { text: "Tracks state " },
      { labels: ["S1"], raw: "[S1]" },
      { text: ". Ports" },
      { labels: ["S2"], raw: "【S2】" },
      { labels: ["S4"], raw: "【S4】" },
      { text: " and " },
      { labels: ["S3", "S5"], raw: "[S3, S5]" },
      { text: "; " },
      { labels: ["S6", "S7"], raw: "[ S6 ; S7 ]" },
      { text: "." },
    ]);
  });

  test("things that only look like citations stay text", () => {
    for (const text of ["[1]", "[Source 1]", "S1 alone", "[S]", "【1】", "[link](S1)"]) {
      expect(splitCitations(text).every((part) => "text" in part)).toBe(true);
    }
  });

  test("citedLabels lists each label once, in order of first appearance", () => {
    expect(citedLabels("A【S3】 b [S1][S3] c [S2, S1] d [S9].")).toEqual(["S3", "S1", "S2", "S9"]);
    expect(citedLabels("The material doesn't cover this.")).toEqual([]);
  });
});

describe("turns", () => {
  const message = (overrides: Partial<StoredMessage>): StoredMessage => ({
    id: "m",
    role: "user",
    mode: "answer",
    text: "",
    status: "complete",
    model: null,
    first_token_ms: null,
    total_ms: null,
    unknown_citations: [],
    created_at: "2026-11-19T10:00:00Z",
    sources: [],
    ...overrides,
  });

  test("stored messages pair up into turns, failed answers say so", () => {
    const turns = turnsFromMessages([
      message({ id: "q1", text: "What is a salt?" }),
      message({
        id: "a1",
        role: "assistant",
        text: "Random data [S1].",
        model: "groq/openai/gpt-oss-120b",
        first_token_ms: 640,
        sources: [
          {
            label: "S1",
            rank: 1,
            material_id: "mat",
            material_title: "CH03",
            page_number: 13,
            page_title: null,
            cited: true,
          },
        ],
      }),
      message({ id: "q2", text: "And a pepper?" }),
      message({ id: "a2", role: "assistant", status: "failed" }),
      message({ id: "q3", text: "Unanswered" }),
    ]);

    expect(turns.map((t) => [t.question, t.answer?.status ?? null])).toEqual([
      ["What is a salt?", "complete"],
      ["And a pepper?", "failed"],
      ["Unanswered", null],
    ]);
    expect(turns[0]!.answer!.sources[0]).toMatchObject({ label: "S1", page: 13, cited: true });
    expect(turns[1]!.answer!.error).toBe("The tutor couldn't answer this one.");
  });

  test("live sources are cited as the text cites them, until done says which", () => {
    const sources = [1, 2].map((n) => ({
      label: `S${n}`,
      material_id: "mat",
      material_title: "CH09",
      page_number: n,
      page_title: null,
    }));
    expect(liveSources(sources, "Tracks【S2】").map((s) => s.cited)).toEqual([false, true]);
    expect(liveSources(sources, "Tracks【S2】", ["S1"]).map((s) => s.cited)).toEqual([true, false]);
  });

  test("the footnote names the model and the measured first words", () => {
    expect(modelName("groq/openai/gpt-oss-120b")).toBe("gpt-oss-120b (Groq)");
    expect(modelName("gemini/gemini-3.5-flash-lite")).toBe("gemini-3.5-flash-lite (Gemini)");
    expect(answeredBy("groq/openai/gpt-oss-120b", 640)).toBe(
      "Answered by gpt-oss-120b (Groq) · first words in 0.6 s (measured)",
    );
    expect(answeredBy("gemini/flash", null)).toBe("Answered by flash (Gemini)");
    expect(answeredBy(null, 640)).toBeNull();
  });

  test("busy providers say when to try again; other errors are shown as they are", () => {
    const hhmm = (date: Date) => date.toISOString().slice(11, 16);
    expect(errorMessage("Trying again after …", "2026-11-19T14:05:00Z", hhmm)).toBe(
      "The free AI providers are busy; try again at 14:05.",
    );
    expect(errorMessage("The answer stopped part-way.", null)).toBe("The answer stopped part-way.");
  });

  test("the live region grows a whole sentence at a time", () => {
    expect(spokenSentences("A stateful firewall tracks connections. It keeps a ta", false)).toEqual(
      ["A stateful firewall tracks connections."],
    );
    expect(spokenSentences("Pi is 3.", false)).toEqual([]); // may still become 3.14
    expect(spokenSentences("Pi is 3.14. Done", true)).toEqual(["Pi is 3.14.", "Done"]);
    expect(spokenSentences("- one\n- two\n", false)).toEqual(["- one", "- two"]);
  });
});
