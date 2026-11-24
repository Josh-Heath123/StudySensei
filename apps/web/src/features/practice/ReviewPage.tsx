import { CircleCheck, Layers } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { PageHeader } from "@/app/PageHeader";
import { EmptyState } from "@/features/modules/EmptyState";
import { useNow } from "@/lib/useNow";
import { Button } from "@/ui/button";

import { useQueue, useReview, type Queue, type QueueCounts } from "./api";
import { GRADE_LABELS, nextDueText, plural, shareRight, type Grade } from "./practiceText";
import { ReviewCard, type Graded } from "./ReviewCard";

/** A learning step due within this long keeps the session open, waiting for it. */
const WAIT_FOR_STEPS_MS = 20 * 60_000;

/**
 * A review session (/practice/review?module=): one item at a time from the queue, which is
 * fetched again after every review, so a card in its learning steps comes back once it's
 * due. Ends when nothing is due (or the student finishes), with what they did.
 */
export function ReviewPage() {
  const [params] = useSearchParams();
  const moduleId = params.get("module") ?? undefined;
  const now = useNow(5_000);
  const [grades, setGrades] = useState<Grade[]>([]);
  const [finished, setFinished] = useState(false);
  // From the last review's result, until the queue is fetched again.
  const [resultCounts, setResultCounts] = useState<QueueCounts | null>(null);
  const [announcement, setAnnouncement] = useState("");
  // The queue as it was when a grade was sent: it still lists that item, so it's not shown
  // again until the refetch that follows the review replaces it.
  const [stale, setStale] = useState<Queue | undefined>(undefined);
  const review = useReview();

  const [refetchEvery, setRefetchEvery] = useState<number | false>(false);
  const queue = useQueue(moduleId, finished ? false : refetchEvery);
  const fresh = queue.data !== undefined && queue.data !== stale;
  const current = fresh ? queue.data.items[0] : undefined;
  const counts = fresh ? queue.data.counts : (resultCounts ?? queue.data?.counts ?? null);
  const waitUntil = counts?.next_due_at ? new Date(counts.next_due_at).getTime() : null;
  // While waiting for a learning step, fetch again once it's due.
  const wanted =
    waitUntil !== null && !current ? Math.max(5_000, waitUntil - now.getTime() + 1_000) : false;
  if (wanted !== refetchEvery && (wanted === false || refetchEvery === false)) {
    setRefetchEvery(wanted);
  }

  async function grade(itemId: string, graded: Graded) {
    setStale(queue.data);
    try {
      const result = await review.mutateAsync({
        itemId,
        grade: graded.grade,
        duration_ms: graded.durationMs,
        answer_text: graded.answerText,
        ai_marking: graded.aiMarking,
        marked_by:
          graded.aiMarking && graded.aiMarking.suggested_grade === graded.grade ? "ai" : "self",
      });
      setGrades((old) => [...old, graded.grade]);
      setResultCounts(result.counts);
      setAnnouncement(`Saved: ${GRADE_LABELS[graded.grade]}. Next card.`);
    } catch {
      // Shown below the card; the same card stays.
      setStale(undefined);
    }
  }

  const waiting =
    fresh &&
    !current &&
    grades.length > 0 &&
    waitUntil !== null &&
    waitUntil - now.getTime() <= WAIT_FOR_STEPS_MS;

  let body;
  if (queue.isError) {
    body = (
      <p role="alert" className="text-danger">
        Couldn&apos;t load your reviews: {queue.error.message}
      </p>
    );
  } else if (finished || (fresh && !current && !waiting)) {
    body =
      grades.length === 0 ? (
        <EmptyState
          icon={Layers}
          title="Nothing to review right now"
          action={
            <Button asChild variant="outline">
              <Link to="/practice">Back to practice</Link>
            </Button>
          }
        >
          {counts?.next_due_at
            ? `Your next review is ${nextDueText(counts.next_due_at, now)}.`
            : "Add a card or generate practice for a topic, and it will show up here."}
        </EmptyState>
      ) : (
        <Summary grades={grades} counts={counts} now={now} />
      );
  } else if (waiting) {
    body = (
      <section
        aria-labelledby="waiting-heading"
        className="bg-surface border-line grid justify-items-start gap-4 rounded-xl border p-6 sm:p-8"
      >
        <h2 id="waiting-heading" className="type-h2">
          A card you&apos;re learning comes back {nextDueText(counts!.next_due_at!, now)}
        </h2>
        <p className="text-muted">
          Learning steps are short on purpose. Wait for it here, or finish for now: it will be due
          the next time you review.
        </p>
        <Button variant="outline" onClick={() => setFinished(true)}>
          Finish now
        </Button>
      </section>
    );
  } else if (!current) {
    body = (
      <div aria-busy="true" className="grid gap-4">
        <p className="sr-only">Loading…</p>
        <div className="skeleton h-64 rounded-xl" />
      </div>
    );
  } else {
    body = (
      <div className="grid gap-4">
        <ReviewCard
          key={`${current.id}-${grades.length}`}
          item={current}
          busy={review.isPending}
          announce={setAnnouncement}
          onGrade={(graded) => void grade(current.id, graded)}
        />
        {review.isError && (
          <p role="alert" className="text-danger text-sm">
            Couldn&apos;t save that grade: {review.error.message}
          </p>
        )}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-muted text-sm">
            {grades.length > 0 ? `${plural(grades.length, "card")} reviewed so far. ` : ""}
            <span className="hidden sm:inline">
              Keys: Space or Enter shows a flashcard&apos;s answer; 1 to 4 grade it.
            </span>
          </p>
          {grades.length > 0 && (
            <Button variant="quiet" onClick={() => setFinished(true)}>
              Finish
            </Button>
          )}
        </div>
      </div>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow={
          <Link to="/practice" className="hover:underline">
            Practice
          </Link>
        }
        title="Review"
      />
      <div className="mx-auto grid max-w-3xl gap-6">{body}</div>
      <p aria-live="polite" className="sr-only">
        {announcement}
      </p>
    </>
  );
}

function Summary({
  grades,
  counts,
  now,
}: {
  grades: Grade[];
  counts: QueueCounts | null;
  now: Date;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  return (
    <section
      aria-labelledby="summary-heading"
      className="bg-surface border-line grid justify-items-start gap-5 rounded-xl border p-6 sm:p-8"
    >
      <CircleCheck aria-hidden className="text-success size-8" />
      <h2 id="summary-heading" ref={heading} tabIndex={-1} className="type-h2 outline-none">
        {plural(grades.length, "card")} reviewed
      </h2>
      <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
        <div>
          <dt className="type-label text-muted">Right</dt>
          <dd className="type-h3 tabular-nums">
            {shareRight(grades)} %{" "}
            <span className="text-muted text-sm font-normal">
              Good or Easy, measured over {plural(grades.length, "review")}
            </span>
          </dd>
        </div>
        <div>
          <dt className="type-label text-muted">Next due</dt>
          <dd className="type-h3">
            {counts?.due_now
              ? `${counts.due_now} due now`
              : counts?.next_due_at
                ? nextDueText(counts.next_due_at, now)
                : "Nothing scheduled"}
          </dd>
        </div>
      </dl>
      <Button asChild>
        <Link to="/practice">Back to practice</Link>
      </Button>
    </section>
  );
}
