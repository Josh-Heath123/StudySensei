import { Layers } from "lucide-react";
import { Link } from "react-router";

import { useQueue } from "@/features/practice/api";
import { countsLine, nextDueText } from "@/features/practice/practiceText";
import { useNow } from "@/lib/useNow";
import { Button } from "@/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/ui/card";

/** Today's reviews (GET /practice/queue): what's due and Start review, or when the next is. */
export function ReviewsCard() {
  const queue = useQueue();
  const now = useNow();
  const counts = queue.data?.counts;
  const line = counts ? countsLine(counts) : "";
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2">
            <Layers aria-hidden className="text-link size-5" />
            Reviews
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {queue.isError ? (
          <p role="alert" className="text-danger text-sm">
            Couldn&apos;t load your reviews: {queue.error.message}
          </p>
        ) : !counts ? (
          <div aria-busy="true" className="skeleton h-12" />
        ) : line ? (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="type-h3 tabular-nums">{line}</p>
            <Button asChild>
              <Link to="/practice/review">Start review</Link>
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-muted">
              {counts.next_due_at ? (
                `Next review ${nextDueText(counts.next_due_at, now)}.`
              ) : (
                <>
                  Nothing to review yet.{" "}
                  <Link to="/practice" className="text-link hover:underline">
                    Add a card or generate practice
                  </Link>
                  .
                </>
              )}
            </p>
            <Button asChild variant="outline">
              <Link to="/practice">Open practice</Link>
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
