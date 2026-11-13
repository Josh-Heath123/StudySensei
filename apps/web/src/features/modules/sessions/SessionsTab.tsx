import { Play } from "lucide-react";
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
    <section aria-labelledby="sessions-heading" className="max-w-3xl">
      <h2 id="sessions-heading" className="type-h3 mb-4">
        Sessions
      </h2>
      <Summary moduleId={moduleId} now={now} />

      {sessions.isPending && <p className="text-muted text-sm">Loading…</p>}
      {sessions.isError && (
        <p role="alert" className="text-danger text-sm">
          {sessions.error.message}
        </p>
      )}
      {sessions.isSuccess && rows.length === 0 && (
        <p className="text-muted border-line rounded-lg border-2 p-6">
          No sessions yet. Start one from the button above.
        </p>
      )}
      {rows.length > 0 && (
        <ol aria-label="Sessions" className="divide-line border-line divide-y border-y">
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
      <dl className="grid gap-4 sm:grid-cols-3">
        {stats.map((stat) => (
          <div key={stat.label} className="border-line rounded-lg border-2 p-4">
            <dt className="text-sm font-semibold">{stat.label}</dt>
            <dd className="type-h2 tabular mt-1">{stat.value}</dd>
          </div>
        ))}
      </dl>
      <p className="text-muted mt-2 text-xs">
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
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">
          <button
            type="button"
            onClick={onOpen}
            className="hover:underline hover:underline-offset-4"
            aria-label={`${formatDue(session.started_at)}, ${topic}`}
          >
            <time dateTime={session.started_at}>{formatDue(session.started_at)}</time> · {topic}
          </button>
          {inProgress && (
            <span className="type-label text-ink ml-3 rounded-md bg-[var(--module)] px-2 py-0.5">
              In progress
            </span>
          )}
        </p>
        <p className="text-muted flex flex-wrap gap-x-3 text-xs">
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
        <Button variant="module" size="sm" asChild>
          <Link to="/session">
            <Play aria-hidden /> Resume
          </Link>
        </Button>
      )}
    </li>
  );
}
