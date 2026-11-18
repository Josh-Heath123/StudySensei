import { formatDue } from "@/lib/dates";
import { formatDuration } from "@/session-engine/format";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/ui/dialog";

import type { TopicNode } from "../api";
import { findTopicName } from "../../session/topics";
import { LoadingRows } from "../LoadingRows";
import { useSessionDetail } from "./api";
import { timelineRows } from "./history";

const clock = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });

/** One session: its reflection and its event timeline. */
export function SessionDetailDialog({
  sessionId,
  topics,
  onClose,
}: {
  sessionId: string;
  topics: TopicNode[];
  onClose: () => void;
}) {
  const detail = useSessionDetail(sessionId);
  const session = detail.data;
  const topic = session ? (findTopicName(topics, session.topic_id) ?? "Whole module") : "";

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{session ? formatDue(session.started_at) : "Session"}</DialogTitle>
          <DialogDescription>{topic}</DialogDescription>
        </DialogHeader>

        {detail.isPending && <LoadingRows label="Loading session…" rows={3} rowClassName="h-10" />}
        {detail.isError && (
          <p role="alert" className="text-danger text-sm">
            {detail.error.message}
          </p>
        )}
        {session && (
          <div className="grid gap-6">
            <p className="tabular text-sm font-medium">
              Active {formatDuration(session.active_seconds * 1000)} · Break{" "}
              {formatDuration(session.break_seconds * 1000)}{" "}
              <span className="text-muted text-xs font-normal">
                (Measured · from {session.events.length} timer events
                {session.state !== "ended" && ", up to the last one"})
              </span>
            </p>

            <section aria-labelledby="reflection-heading">
              <h3 id="reflection-heading" className="type-label text-muted mb-2">
                Reflection
              </h3>
              {session.focus_rating === null ? (
                <p className="text-muted text-sm">
                  {session.state === "ended" ? "No reflection was saved." : "Still in progress."}
                </p>
              ) : (
                <dl className="bg-surface grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 rounded-lg p-4 text-sm">
                  <dt className="text-muted">Focus</dt>
                  <dd>{session.focus_rating}/5</dd>
                  <dt className="text-muted">Covered</dt>
                  <dd className="break-words whitespace-pre-line">
                    {session.covered_notes ?? "Nothing noted"}
                  </dd>
                  {session.topic_ratings.map((rating) => (
                    <div key={rating.topic_id} className="contents">
                      <dt className="text-muted">
                        {findTopicName(topics, rating.topic_id) ?? "Deleted topic"}
                      </dt>
                      <dd>Confidence {rating.confidence}/5</dd>
                    </div>
                  ))}
                </dl>
              )}
            </section>

            <section aria-labelledby="timeline-heading">
              <h3 id="timeline-heading" className="type-label text-muted mb-2">
                Timeline
              </h3>
              <ol
                aria-label="Timeline"
                className="bg-surface divide-line divide-y overflow-hidden rounded-lg"
              >
                {timelineRows(session.events).map((row) => (
                  <li key={row.id} className="flex gap-4 px-4 py-2 text-sm">
                    <time dateTime={row.at} className="text-muted tabular w-12 shrink-0">
                      {clock.format(new Date(row.at))}
                    </time>
                    <span>{row.label}</span>
                  </li>
                ))}
              </ol>
            </section>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
