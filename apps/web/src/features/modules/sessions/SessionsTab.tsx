import { Play, Timer } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { formatDue } from "@/lib/dates";
import { useNow } from "@/lib/useNow";
import { formatDuration } from "@/session-engine/format";
import { Button } from "@/ui/button";

import { useTopicTree, type TopicNode } from "../api";
import { findTopicName } from "../../session/topics";
import { useModuleSessions, useSessionSummary, type SessionRow } from "./api";
import { activeSecondsAt, startOfWeek } from "./history";
import { EmptyState } from "../EmptyState";
import { LoadingRows } from "../LoadingRows";
import { SessionDetailDialog } from "./SessionDetailDialog";

const minutes = (seconds: number) => formatDuration(seconds * 1000);
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** Session history for one module: a measured summary, then sessions newest first. */
export function SessionsTab({ moduleId }: { moduleId: string }) {
  const now = useNow();
  const sessions = useModuleSessions(moduleId);
  const tree = useTopicTree(moduleId);
  const [openId, setOpenId] = useState<string | null>(null);

  const rows = sessions.data?.pages.flatMap((page) => page.items) ?? [];
  const topics = tree.data ?? [];

  return (
    <section aria-labelledby="sessions-heading">
      <h2 id="sessions-heading" className="type-h2 mb-6">
        Sessions
      </h2>
      <Summary moduleId={moduleId} now={now} />

      {sessions.isPending && <LoadingRows label="Loading sessions…" />}
      {sessions.isError && (
        <p role="alert" className="text-danger text-sm">
          {sessions.error.message}
        </p>
      )}
      {sessions.isSuccess && rows.length === 0 && (
        <EmptyState icon={Timer}>No sessions yet. Start one from the button above.</EmptyState>
      )}
      {rows.length > 0 && (
        <ol
          aria-label="Sessions"
          className="surface-card divide-line divide-y overflow-hidden rounded-xl"
        >
          {rows.map((row) => (
            <SessionItem
              key={row.id}
              session={row}
              topics={topics}
              now={now.getTime()}
              onOpen={() => setOpenId(row.id)}
            />
          ))}
        </ol>
      )}
      {sessions.hasNextPage && (
        <Button
          variant="outline"
          className="mt-4"
          disabled={sessions.isFetchingNextPage}
          onClick={() => void sessions.fetchNextPage()}
        >
          {sessions.isFetchingNextPage ? "Loading…" : "Show older sessions"}
        </Button>
      )}

      {openId && (
        <SessionDetailDialog sessionId={openId} topics={topics} onClose={() => setOpenId(null)} />
      )}
    </section>
  );
}

function Summary({ moduleId, now }: { moduleId: string; now: Date }) {
  const summary = useSessionSummary(moduleId, startOfWeek(now));
  if (!summary.data) return null;
  const { session_count, active_seconds, week_active_seconds } = summary.data;
  const stats = [
    { label: "This week", value: minutes(week_active_seconds) },
    { label: "All time", value: minutes(active_seconds) },
    { label: "Sessions", value: String(session_count) },
  ];
  return (
    <section aria-label="Study time" className="mb-6">
      <dl className="grid grid-cols-1 gap-3 min-[480px]:grid-cols-3 sm:gap-4">
        {stats.map((stat) => (
          <div key={stat.label} className="surface-card rounded-xl px-5 py-4">
            <dt className="type-label text-muted">{stat.label}</dt>
            <dd className="type-h2 tabular mt-2">{stat.value}</dd>
          </div>
        ))}
      </dl>
      <p className="text-muted mt-3 px-1 text-xs">
        Measured · active time from timer events, {plural(session_count, "session")}. This week
        starts Monday.
      </p>
    </section>
  );
}

function SessionItem({
  session,
  topics,
  now,
  onOpen,
}: {
  session: SessionRow;
  topics: TopicNode[];
  now: number;
  onOpen: () => void;
}) {
  const inProgress = session.state !== "ended";
  const topic = findTopicName(topics, session.topic_id) ?? "Whole module";
  const ratings = session.topic_ratings.map((rating) => ({
    name: findTopicName(topics, rating.topic_id) ?? "Deleted topic",
    confidence: rating.confidence,
  }));

  return (
    <li className="hover:bg-subtle flex flex-wrap items-center gap-x-4 gap-y-2 py-3 pr-3 pl-4 transition-colors sm:pl-5">
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm font-medium">
          <button
            type="button"
            onClick={onOpen}
            className="cursor-pointer rounded-sm text-left underline-offset-4 hover:underline"
            aria-label={`${formatDue(session.started_at)}, ${topic}`}
          >
            <time dateTime={session.started_at}>{formatDue(session.started_at)}</time> · {topic}
          </button>
          {inProgress && (
            <span className="type-label text-on-fill rounded-sm bg-[var(--module)] px-2 py-0.5">
              In progress
            </span>
          )}
        </p>
        <p className="text-muted tabular mt-0.5 flex flex-wrap gap-x-3 text-xs">
          <span>Active {minutes(activeSecondsAt(session, now))}</span>
          <span>Break {minutes(session.break_seconds)}</span>
          {session.focus_rating !== null ? (
            <span>Focus {session.focus_rating}/5</span>
          ) : (
            !inProgress && <span>No reflection</span>
          )}
          {ratings.map((rating) => (
            <span key={rating.name}>
              {rating.name} {rating.confidence}/5
            </span>
          ))}
        </p>
      </div>
      {inProgress && (
        <Button variant="outline" size="sm" asChild>
          <Link to="/session">
            <Play aria-hidden /> Resume
          </Link>
        </Button>
      )}
    </li>
  );
}
