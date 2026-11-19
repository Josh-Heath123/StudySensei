import { ChevronRight, RotateCcw } from "lucide-react";
import { lazy, Suspense } from "react";

import { plainText } from "@/features/modules/materials/searchResults";
import { cn } from "@/lib/utils";
import { Button } from "@/ui/button";

import { SourcesContext, sourceLabel, type OpenSource } from "./sourcesContext";
import { answeredBy, errorMessage, type AnswerView, type SourceView } from "./turns";

// KaTeX and the Markdown pipeline load on the first answer, not with the app.
const AnswerMarkdown = lazy(() => import("./AnswerMarkdown"));

/**
 * One answer on a solid surface: the text (Markdown with maths and citation chips), a caret
 * while it streams, what happened if it didn't finish, its sources, and who answered.
 * An answer saying the material doesn't cover the question is just an answer.
 */
export function TutorAnswer({
  answer,
  onOpen,
  onRetry,
}: {
  answer: AnswerView;
  onOpen: OpenSource;
  onRetry?: () => void;
}) {
  const streaming = answer.status === "waiting" || answer.status === "streaming";
  const byline = answeredBy(answer.model, answer.firstTokenMs);
  return (
    <SourcesContext.Provider value={{ sources: answer.sources, open: onOpen }}>
      <div className="grid gap-3">
        {answer.status === "waiting" && !answer.text && (
          <p className="text-muted flex items-center gap-2 text-sm">
            <span aria-hidden className="answer-caret" />
            {answer.sources.length > 0
              ? `Reading ${answer.sources.length} ${answer.sources.length === 1 ? "page" : "pages"} of your material…`
              : "Finding the matching pages…"}
          </p>
        )}
        {answer.text && (
          <div className="answer-prose">
            <Suspense fallback={<p className="whitespace-pre-wrap">{answer.text}</p>}>
              <AnswerMarkdown text={answer.text} />
            </Suspense>
            {streaming && <span aria-hidden className="answer-caret" />}
          </div>
        )}
        {answer.status === "truncated" && (
          <p className="text-muted text-sm">The answer was cut off at the model's length limit.</p>
        )}
        {answer.status === "stopped" && <p className="text-muted text-sm">Stopped.</p>}
        {answer.status === "failed" && (
          <div className="flex flex-wrap items-center gap-3">
            <p role="alert" className="text-danger min-w-0 flex-1 text-sm">
              {errorMessage(answer.error ?? "The tutor couldn't answer this one.", answer.retryAt)}
            </p>
            {onRetry && (
              <Button variant="outline" size="sm" onClick={onRetry}>
                <RotateCcw aria-hidden />
                Retry
              </Button>
            )}
          </div>
        )}
        {!streaming && answer.sources.length > 0 && (
          <SourceList sources={answer.sources} onOpen={onOpen} />
        )}
        {!streaming && byline && <p className="text-muted text-xs">{byline}</p>}
      </div>
    </SourcesContext.Provider>
  );
}

/** Cited sources first and highlighted; the others folded away. */
function SourceList({ sources, onOpen }: { sources: SourceView[]; onOpen: OpenSource }) {
  const cited = sources.filter((s) => s.cited);
  const others = sources.filter((s) => !s.cited);
  return (
    <div className="grid gap-1.5">
      {cited.length > 0 && (
        <ul aria-label="Cited sources" className="grid gap-1">
          {cited.map((source) => (
            <SourceRow key={source.label} source={source} onOpen={onOpen} cited />
          ))}
        </ul>
      )}
      {others.length > 0 && (
        <details className="group">
          <summary className="text-muted hover:text-fg flex w-fit cursor-pointer list-none items-center gap-1 text-xs font-medium [&::-webkit-details-marker]:hidden">
            <ChevronRight
              aria-hidden
              className="size-3.5 transition-transform group-open:rotate-90"
            />
            {cited.length > 0
              ? `${others.length} more ${others.length === 1 ? "source" : "sources"} it was given`
              : `${others.length} ${others.length === 1 ? "source" : "sources"} it was given (none cited)`}
          </summary>
          <ul aria-label="Other sources" className="mt-1 grid gap-1">
            {others.map((source) => (
              <SourceRow key={source.label} source={source} onOpen={onOpen} />
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function SourceRow({
  source,
  onOpen,
  cited = false,
}: {
  source: SourceView;
  onOpen: OpenSource;
  cited?: boolean;
}) {
  const label = plainText(sourceLabel(source));
  return (
    <li>
      <button
        type="button"
        disabled={source.materialId === null}
        onClick={() => onOpen(source)}
        className={cn(
          "flex w-full cursor-pointer items-baseline gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors disabled:cursor-default",
          cited ? "bg-accent-soft/60 hover:bg-accent-soft" : "text-muted hover:bg-subtle",
        )}
      >
        <span className={cn("text-xs font-semibold tabular-nums", cited && "text-link")}>
          {source.label}
        </span>
        <span className="min-w-0 truncate">{label}</span>
        {source.materialId === null && <span className="text-muted text-xs">(deleted)</span>}
      </button>
    </li>
  );
}
