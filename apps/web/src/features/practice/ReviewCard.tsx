import { Check, Sparkles, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { Label } from "@/ui/label";
import { Textarea } from "@/ui/textarea";

import { useMarkAnswer, usePreview, type AiMarking, type PracticeItem } from "./api";
import { GradeButtons } from "./GradeButtons";
import { GRADE_LABELS, MARKING_PRIVACY, suggestFromTicks, type Grade } from "./practiceText";
import { SourceChips } from "./SourceChips";

export type Graded = {
  grade: Grade;
  durationMs: number;
  answerText: string | null;
  aiMarking: AiMarking | null;
};

const VERDICTS = {
  correct: "Correct",
  partly: "Partly right",
  incorrect: "Not yet",
} as const;

/** Keys typed into a field, or Space and Enter on a button, belong to that element. */
function ownedByTarget(event: KeyboardEvent): boolean {
  const target = event.target as HTMLElement | null;
  if (!target) return false;
  if (target.closest("input, textarea, select, [contenteditable='true']")) return true;
  return (event.key === " " || event.key === "Enter") && target.closest("button, a") !== null;
}

/**
 * One item in a review (docs/DESIGN.md "The review card"): a solid surface, since it's
 * reading material. A flashcard shows its prompt, then the answer (Space or Enter). A short
 * answer takes a typed answer, then either the AI's check against the reference (optional)
 * or the reference with its key points to tick. Then the four grades (keys 1-4), with any
 * suggestion outlined. The student always presses the grade.
 */
export function ReviewCard({
  item,
  busy,
  onGrade,
  announce,
}: {
  item: PracticeItem;
  busy: boolean;
  onGrade: (graded: Graded) => void;
  announce: (message: string) => void;
}) {
  // When the question was shown: duration_ms runs from here to the grade.
  const shownAt = useRef(0);
  const promptRef = useRef<HTMLHeadingElement>(null);
  const revealRef = useRef<HTMLDivElement>(null);
  const [revealed, setRevealed] = useState(false);
  const [answer, setAnswer] = useState("");
  const [ticks, setTicks] = useState<boolean[]>(() => (item.key_points ?? []).map(() => false));
  const [marking, setMarking] = useState<AiMarking | null>(null);
  const mark = useMarkAnswer();
  const preview = usePreview(item.id);
  const answerId = useId();
  const short = item.kind === "short_answer";
  const keyPoints = item.key_points ?? [];

  const suggested: Grade | null = marking
    ? (marking.suggested_grade as Grade)
    : short && revealed
      ? suggestFromTicks(ticks.filter(Boolean).length, keyPoints.length)
      : null;

  // Focus the new question, and start its clock.
  useEffect(() => {
    shownAt.current = Date.now();
    promptRef.current?.focus();
  }, []);

  function reveal() {
    setRevealed(true);
    announce(short ? "Reference answer shown. Tick the key points you made." : "Answer shown.");
    requestAnimationFrame(() => revealRef.current?.focus());
  }

  function grade(chosen: Grade) {
    if (busy) return;
    onGrade({
      grade: chosen,
      durationMs: Date.now() - shownAt.current,
      answerText: short && answer.trim() ? answer.trim() : null,
      aiMarking: marking,
    });
  }

  async function checkWithAi() {
    try {
      const found = await mark.mutateAsync({ itemId: item.id, answer: answer.trim() });
      setMarking(found);
      setRevealed(true);
      const covered = found.coverage.filter((c) => c.covered).length;
      announce(
        `${VERDICTS[found.verdict]}: ${covered} of ${found.coverage.length} key points. ` +
          `The AI suggests ${GRADE_LABELS[found.suggested_grade as Grade]}.`,
      );
      requestAnimationFrame(() => revealRef.current?.focus());
    } catch {
      // Shown below; the reference is still there to mark it yourself.
    }
  }

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey || ownedByTarget(event)) return;
      if (!revealed && !short && (event.key === " " || event.key === "Enter")) {
        event.preventDefault();
        reveal();
      } else if (revealed && ["1", "2", "3", "4"].includes(event.key)) {
        event.preventDefault();
        grade(Number(event.key) as Grade);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <article
      aria-labelledby={`${answerId}-prompt`}
      className="bg-surface border-line grid gap-6 rounded-xl border p-5 shadow-sm sm:p-8"
    >
      <header className="grid gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{short ? "Short answer" : "Flashcard"}</Badge>
          <Badge variant="outline">{item.origin === "ai" ? "AI" : "Yours"}</Badge>
        </div>
        <h2
          id={`${answerId}-prompt`}
          ref={promptRef}
          tabIndex={-1}
          className="type-h2 [overflow-wrap:anywhere] outline-none"
        >
          {item.prompt}
        </h2>
      </header>

      {short && (
        <div className="grid gap-2">
          <Label htmlFor={`${answerId}-answer`}>Your answer</Label>
          <Textarea
            id={`${answerId}-answer`}
            value={answer}
            maxLength={2000}
            rows={4}
            readOnly={revealed}
            onChange={(event) => setAnswer(event.target.value)}
          />
          {!marking && (
            <div className="grid gap-1.5">
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  disabled={!answer.trim() || mark.isPending || busy}
                  onClick={() => void checkWithAi()}
                >
                  <Sparkles aria-hidden />
                  {mark.isPending ? "Checking…" : "Check with AI"}
                </Button>
                {!revealed && (
                  <Button variant="quiet" onClick={reveal}>
                    Show reference
                  </Button>
                )}
              </div>
              <p className="text-muted text-xs">{MARKING_PRIVACY}</p>
              {mark.isError && (
                <p role="alert" className="text-danger text-sm">
                  {mark.error.message} You can still show the reference and mark it yourself.
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {!short && !revealed && (
        <div>
          <Button onClick={reveal} aria-keyshortcuts="Space Enter">
            Show answer
          </Button>
          <p className="text-muted mt-2 text-xs">Or press Space or Enter.</p>
        </div>
      )}

      {revealed && (
        <div ref={revealRef} tabIndex={-1} className="grid gap-5 outline-none">
          {marking && <AiResult marking={marking} />}
          <section aria-label="Reference answer" className="bg-subtle grid gap-2 rounded-lg p-4">
            <h3 className="type-label text-muted">{short ? "Reference answer" : "Answer"}</h3>
            <p className="[overflow-wrap:anywhere] whitespace-pre-line">{item.answer}</p>
            <SourceChips item={item} />
          </section>
          {short && !marking && (
            <fieldset className="grid gap-2">
              <legend className="type-label mb-1">Tick the key points your answer made</legend>
              {keyPoints.map((point, index) => (
                <label
                  key={point}
                  className="hover:bg-subtle flex min-h-10 cursor-pointer items-start gap-3 rounded-md px-2 py-2"
                >
                  <input
                    type="checkbox"
                    className="accent-primary mt-1 size-4"
                    checked={ticks[index] ?? false}
                    onChange={(event) =>
                      setTicks((old) => old.map((t, i) => (i === index ? event.target.checked : t)))
                    }
                  />
                  <span>{point}</span>
                </label>
              ))}
              <p className="text-muted text-sm" aria-live="polite">
                {ticks.filter(Boolean).length} of {keyPoints.length} ticked:{" "}
                {GRADE_LABELS[suggestFromTicks(ticks.filter(Boolean).length, keyPoints.length)]}{" "}
                suggested.
              </p>
            </fieldset>
          )}
          <GradeButtons
            preview={preview.data}
            suggested={suggested}
            suggestedBy={marking ? "the AI" : "your ticks"}
            disabled={busy}
            onGrade={grade}
          />
        </div>
      )}
    </article>
  );
}

function AiResult({ marking }: { marking: AiMarking }) {
  const covered = marking.coverage.filter((c) => c.covered).length;
  return (
    <section aria-label="The AI's check" className="border-line grid gap-3 rounded-lg border p-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="type-h3">{VERDICTS[marking.verdict]}</h3>
        <p className="text-muted text-sm">
          {covered} of {marking.coverage.length} key points · checked by {marking.model}
        </p>
      </div>
      <ul className="grid gap-1.5">
        {marking.coverage.map((c) => (
          <li key={c.index} className="flex items-start gap-2">
            {c.covered ? (
              <Check aria-hidden className="text-success mt-0.5 size-4 shrink-0" />
            ) : (
              <X aria-hidden className="text-danger mt-0.5 size-4 shrink-0" />
            )}
            <span>
              <span className="sr-only">{c.covered ? "Covered: " : "Missing: "}</span>
              {c.key_point}
            </span>
          </li>
        ))}
      </ul>
      <p>{marking.feedback}</p>
      <p className="text-muted text-sm">
        It suggests {GRADE_LABELS[marking.suggested_grade as Grade]}. You choose the grade.
      </p>
    </section>
  );
}
