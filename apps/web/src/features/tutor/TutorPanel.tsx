import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { PagesDialog } from "@/features/modules/materials/PagesDialog";
import { cn } from "@/lib/utils";
import { Button } from "@/ui/button";
import { TooltipProvider } from "@/ui/tooltip";

import { PRIVACY_NOTE, privacyNoteSeen, rememberPrivacyNote } from "./storage";
import { TutorAnswer } from "./TutorAnswer";
import { spokenSentences, type SourceView, type Turn } from "./turns";
import type { useTutor } from "./useTutor";

type Tutor = ReturnType<typeof useTutor>;

/**
 * The tutor's conversation and its input bar (docs/DESIGN.md "Tutor panel"). The answers
 * are reading material on a solid surface; the input bar is glass. Enter sends,
 * Shift+Enter adds a line, and focus comes back to the box after sending.
 */
export function TutorPanel({ tutor, autoFocus = false }: { tutor: Tutor; autoFocus?: boolean }) {
  const [draft, setDraft] = useState("");
  const [viewing, setViewing] = useState<SourceView | null>(null);
  const [noteSeen, setNoteSeen] = useState(privacyNoteSeen);
  const input = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const last = tutor.turns.at(-1);

  useEffect(() => {
    if (autoFocus) input.current?.focus();
  }, [autoFocus]);

  // Keep the newest text in view as it streams (instant: no smooth scrolling to animate).
  const lastText = last?.answer?.text;
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [tutor.turns.length, lastText]);

  function send(question: string) {
    if (!question.trim() || tutor.busy || !tutor.ready) return;
    void tutor.send(question);
    setDraft("");
    if (!noteSeen) {
      rememberPrivacyNote();
      setNoteSeen(true);
    }
    input.current?.focus();
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    send(draft);
  }

  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      send(draft);
    }
  }

  return (
    <TooltipProvider>
      <div className="flex min-h-0 flex-1 flex-col">
        <div
          role="log"
          aria-label="Tutor conversation"
          className="surface-card mx-3 grid min-h-0 flex-1 content-start gap-5 overflow-y-auto rounded-xl p-4 sm:p-5"
        >
          {tutor.restoring && (
            <p aria-busy="true" className="text-muted text-sm">
              Loading this session's questions…
            </p>
          )}
          {tutor.loadError && (
            <p role="alert" className="text-danger text-sm">
              {tutor.loadError}
            </p>
          )}
          {!tutor.restoring && tutor.turns.length === 0 && (
            <p className="text-muted text-sm">
              Ask anything about this topic. Answers come from your own material, with links to the
              pages they used.
            </p>
          )}
          {tutor.turns.map((turn) => (
            <TurnView
              key={turn.key}
              turn={turn}
              onOpen={setViewing}
              onRetry={
                turn === last && turn.answer?.status === "failed" && !tutor.busy
                  ? () => void tutor.send(turn.question, turn.mode)
                  : undefined
              }
            />
          ))}
          <div ref={end} />
        </div>

        <LiveAnswer turn={last} />

        <form onSubmit={submit} className="glass m-3 grid gap-2 rounded-2xl p-2">
          {!noteSeen && <p className="text-muted px-2 pt-1 text-xs">{PRIVACY_NOTE}</p>}
          {/* Room for "Explain differently", "Give an example" and "Quiz me" (task 4). */}
          <div className="flex items-end gap-2">
            {/* Room for push-to-talk (task 5). */}
            <label htmlFor="tutor-question" className="sr-only">
              Ask about this topic
            </label>
            <textarea
              id="tutor-question"
              ref={input}
              value={draft}
              rows={1}
              maxLength={2000}
              disabled={!tutor.ready}
              placeholder={tutor.ready ? "Ask about this topic…" : "Connecting to the session…"}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={keyDown}
              className={cn(
                "bg-surface text-fg placeholder:text-muted border-line-strong field-sizing-content max-h-40 min-h-11 min-w-0 flex-1 resize-none rounded-xl border px-3 py-2.5 text-[15px] outline-none",
                "focus-visible:border-ring disabled:opacity-60",
              )}
            />
            {tutor.busy ? (
              <Button type="button" variant="outline" size="icon" onClick={tutor.stop}>
                <Square aria-hidden className="fill-current" />
                <span className="sr-only">Stop</span>
              </Button>
            ) : (
              <Button type="submit" size="icon" disabled={!draft.trim() || !tutor.ready}>
                <ArrowUp aria-hidden />
                <span className="sr-only">Send</span>
              </Button>
            )}
          </div>
        </form>

        {viewing && viewing.materialId !== null && (
          <PagesDialog
            material={{ id: viewing.materialId, title: viewing.title }}
            initialPage={viewing.page}
            onClose={() => setViewing(null)}
          />
        )}
      </div>
    </TooltipProvider>
  );
}

function TurnView({
  turn,
  onOpen,
  onRetry,
}: {
  turn: Turn;
  onOpen: (source: SourceView) => void;
  onRetry?: () => void;
}) {
  return (
    <article aria-label={`Question: ${turn.question}`} className="grid gap-3">
      <p className="bg-subtle ml-6 justify-self-end rounded-lg px-3 py-2 text-[15px] whitespace-pre-wrap">
        {turn.question}
      </p>
      {turn.answer ? (
        <TutorAnswer answer={turn.answer} onOpen={onOpen} onRetry={onRetry} />
      ) : (
        <p className="text-muted text-sm">No answer was saved for this question.</p>
      )}
    </article>
  );
}

/**
 * For screen readers: the answer being written, a sentence at a time (polite), rather than
 * every token. Each new sentence is its own paragraph, so only that one is read out.
 */
function LiveAnswer({ turn }: { turn: Turn | undefined }) {
  const answer = turn?.key === "live" ? turn.answer : null;
  const finished = answer !== null && answer.status !== "waiting" && answer.status !== "streaming";
  const sentences = answer ? spokenSentences(answer.text, finished) : [];
  return (
    <div aria-live="polite" className="sr-only">
      {sentences.map((sentence, index) => (
        <p key={index}>{sentence}</p>
      ))}
    </div>
  );
}
