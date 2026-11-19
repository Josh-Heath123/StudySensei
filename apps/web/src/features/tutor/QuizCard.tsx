import { Check, X } from "lucide-react";
import { lazy, Suspense, useState } from "react";

import { cn } from "@/lib/utils";
import { Button } from "@/ui/button";

import {
  firstUnanswered,
  isRight,
  LETTERS,
  QUIZ_SIZE,
  score,
  withAnswer,
  type Quiz,
  type QuizAnswers,
} from "./quiz";

const AnswerMarkdown = lazy(() => import("./AnswerMarkdown"));

/**
 * One question at a time. The student picks an option; code grades it (never the model);
 * then the explanation, with its citation chips, and "Next". Picks are saved as they're
 * made, so a reload comes back to the first question not answered yet.
 */
export function QuizCard({
  quiz,
  answers: saved,
  onAnswer,
}: {
  quiz: Quiz;
  answers: QuizAnswers;
  /** Save the picks (all of them, one per question). */
  onAnswer: (answers: QuizAnswers) => Promise<void>;
}) {
  const [answers, setAnswers] = useState<QuizAnswers>(() =>
    quiz.questions.map((_, i) => saved[i] ?? null),
  );
  const [index, setIndex] = useState(() => firstUnanswered(quiz, answers));
  const [error, setError] = useState<string | null>(null);
  const total = quiz.questions.length;

  if (index >= total) return <QuizSummary quiz={quiz} answers={answers} />;

  const question = quiz.questions[index]!;
  const pick = answers[index] ?? null;
  const answered = pick !== null;

  async function choose(option: number) {
    if (answered) return;
    const next = withAnswer(quiz, answers, index, option);
    setAnswers(next);
    setError(null);
    try {
      await onAnswer(next);
    } catch (failed) {
      setError(`Your answer is shown but wasn't saved: ${(failed as Error).message}`);
    }
  }

  return (
    <section aria-label="Quiz" className="grid gap-3">
      <p className="type-label text-muted">
        Question {index + 1} of {total}
      </p>
      {index === 0 && total < QUIZ_SIZE && (
        <p className="text-muted text-sm">
          Only {total} {total === 1 ? "question" : "questions"} could be based on your sources.
        </p>
      )}
      <p className="text-[15px] font-semibold">{question.prompt}</p>
      <ul aria-label={`Options for question ${index + 1}`} className="grid gap-1.5">
        {question.options.map((option, i) => {
          const chosen = pick === i;
          const correct = answered && i === question.correct;
          return (
            <li key={i}>
              <button
                type="button"
                disabled={answered}
                aria-pressed={chosen}
                aria-label={`${LETTERS[i]}. ${option}${correct ? " (correct answer)" : chosen ? " (your answer)" : ""}`}
                onClick={() => void choose(i)}
                className={cn(
                  "flex w-full cursor-pointer items-start gap-2.5 rounded-lg border px-3 py-2.5 text-left text-[15px] transition-colors disabled:cursor-default",
                  !answered && "border-line-strong bg-surface hover:bg-subtle",
                  answered && "border-line",
                  correct && "border-success bg-success/10",
                  chosen && !correct && "border-danger bg-danger/10",
                )}
              >
                <span className="text-muted w-4 shrink-0 font-semibold">{LETTERS[i]}</span>
                <span className="min-w-0 flex-1">{option}</span>
                {correct && (
                  <span className="text-success flex items-center gap-1 text-xs font-semibold">
                    <Check aria-hidden className="size-4" />
                    Correct answer
                  </span>
                )}
                {chosen && !correct && (
                  <span className="text-danger flex items-center gap-1 text-xs font-semibold">
                    <X aria-hidden className="size-4" />
                    Your answer
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
      {answered && (
        <div className="grid gap-2" aria-live="polite">
          <p
            className={cn(
              "text-sm font-semibold",
              isRight(question, pick) ? "text-success" : "text-danger",
            )}
          >
            {isRight(question, pick)
              ? "Right."
              : `Not quite: the answer is ${LETTERS[question.correct]}.`}
          </p>
          <div className="answer-prose text-[15px]">
            <Suspense fallback={<p>{question.explanation}</p>}>
              <AnswerMarkdown text={question.explanation} />
            </Suspense>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="justify-self-start"
            onClick={() => setIndex(index + 1)}
          >
            {index + 1 < total ? "Next" : "See how you did"}
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-danger text-sm">
          {error}
        </p>
      )}
    </section>
  );
}

function QuizSummary({ quiz, answers }: { quiz: Quiz; answers: QuizAnswers }) {
  const { right, answered } = score(quiz, answers);
  return (
    <section aria-label="Quiz results" className="grid gap-2">
      <p className="text-[15px] font-semibold">
        You got {right} of {answered} right.
      </p>
      <ol aria-label="Your answers" className="grid gap-2.5">
        {quiz.questions.map((question, i) => {
          const pick = answers[i] ?? null;
          const good = isRight(question, pick);
          const correct = `${LETTERS[question.correct]}. ${question.options[question.correct]}`;
          return (
            <li key={i} className="flex items-start gap-2 text-sm">
              {good ? (
                <Check aria-hidden className="text-success mt-0.5 size-4 shrink-0" />
              ) : (
                <X aria-hidden className="text-danger mt-0.5 size-4 shrink-0" />
              )}
              <div className="grid min-w-0 gap-0.5">
                <p>
                  <span className={cn("font-semibold", good ? "text-success" : "text-danger")}>
                    {good ? "Right" : pick === null ? "Not answered" : "Wrong"}
                  </span>
                  <span className="text-muted"> · </span>
                  {question.prompt}
                </p>
                {good ? (
                  <p className="text-muted">Your answer: {correct}</p>
                ) : (
                  <p className="text-muted">
                    {pick !== null && (
                      <>
                        Your answer: {LETTERS[pick]}. {question.options[pick]}
                        <span> · </span>
                      </>
                    )}
                    <span className="text-fg">Correct: {correct}</span>
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      <p className="text-muted text-xs">
        Practice only: this doesn't change your progress or plan.
      </p>
    </section>
  );
}
