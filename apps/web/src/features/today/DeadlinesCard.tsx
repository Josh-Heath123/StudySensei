import { useState } from "react";
import { Link } from "react-router";

import { formatDue, relativeDay } from "@/lib/dates";
import { cn } from "@/lib/utils";
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/ui/card";

import { useModules } from "../modules/api";
import { useUpdateAssessment } from "../modules/assessments/api";
import { useUpdateTask } from "../modules/tasks/api";
import { useOpenTasks, useUpcomingAssessments } from "./api";
import { buildDeadlines, type Deadline } from "./deadlines";

export function DeadlinesCard() {
  const modules = useModules();
  const assessments = useUpcomingAssessments();
  const tasks = useOpenTasks();
  const updateAssessment = useUpdateAssessment();
  const updateTask = useUpdateTask();
  const [error, setError] = useState<string | null>(null);

  const failed = [modules, assessments, tasks].find((q) => q.isError);
  const ready = modules.data && assessments.data && tasks.data;

  function act(promise: Promise<unknown>) {
    setError(null);
    promise.catch((err: Error) => setError(err.message));
  }

  let body;
  if (failed) {
    body = (
      <p role="alert" className="text-destructive text-sm">
        Couldn't load deadlines: {failed.error?.message}
      </p>
    );
  } else if (!ready) {
    body = <p className="text-muted-foreground text-sm">Loading…</p>;
  } else if (modules.data.length === 0) {
    body = (
      <EmptyState
        title="No modules yet"
        text="Add the modules you're taking, then their tests, exams and assignments. Deadlines from every module show up here."
        action="Add a module"
      />
    );
  } else {
    const { groups, undatedTasks } = buildDeadlines(assessments.data, tasks.data, modules.data);
    const undatedNote = undatedTasks > 0 && (
      <p className="text-muted-foreground mt-4 text-xs">
        {undatedTasks === 1
          ? "1 open task has no due date."
          : `${undatedTasks} open tasks have no due date.`}
      </p>
    );
    body =
      groups.length === 0 ? (
        <>
          <EmptyState
            title="Nothing due"
            text="No upcoming assessments or open tasks with a date. Add dates in a module and they'll show up here."
            action="Go to modules"
          />
          {undatedNote}
        </>
      ) : (
        <>
          <div className="space-y-5">
            {groups.map((group) => (
              <section key={group.key} aria-labelledby={`deadlines-${group.key}`}>
                <h3
                  id={`deadlines-${group.key}`}
                  className={cn(
                    "mb-1.5 text-xs font-semibold tracking-wide uppercase",
                    group.key === "overdue" ? "text-destructive" : "text-muted-foreground",
                  )}
                >
                  {group.label} · {group.items.length}
                </h3>
                <ul aria-label={group.label} className="divide-y rounded-lg border">
                  {group.items.map((item) => (
                    <DeadlineRow
                      key={item.key}
                      item={item}
                      onDone={() =>
                        act(
                          item.type === "task"
                            ? updateTask.mutateAsync({ id: item.id, changes: { status: "done" } })
                            : updateAssessment.mutateAsync({
                                id: item.id,
                                changes: { status: "completed" },
                              }),
                        )
                      }
                    />
                  ))}
                </ul>
              </section>
            ))}
          </div>
          {undatedNote}
        </>
      );
  }

  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle>Upcoming deadlines</CardTitle>
        <CardDescription>Assessments and open tasks across all your modules.</CardDescription>
      </CardHeader>
      <CardContent>
        {error && (
          <p role="alert" className="text-destructive mb-3 text-sm">
            {error}
          </p>
        )}
        {body}
      </CardContent>
    </Card>
  );
}

function EmptyState({ title, text, action }: { title: string; text: string; action: string }) {
  return (
    <div className="rounded-lg border border-dashed p-6 text-center">
      <p className="font-medium">{title}</p>
      <p className="text-muted-foreground mx-auto mt-1 max-w-md text-sm">{text}</p>
      <Button asChild variant="outline" className="mt-4">
        <Link to="/modules">{action}</Link>
      </Button>
    </div>
  );
}

function DeadlineRow({ item, onDone }: { item: Deadline; onDone: () => void }) {
  const tab = item.type === "task" ? "tasks" : "assessments";
  return (
    <li className="flex items-center gap-3 px-4 py-2.5">
      {item.type === "task" ? (
        <input
          type="checkbox"
          aria-label={`Done: ${item.title}`}
          checked={false}
          onChange={onDone}
          className="accent-primary size-4 shrink-0"
        />
      ) : (
        <span aria-hidden className="size-4 shrink-0" />
      )}
      <div className="min-w-0 flex-1">
        <Link
          to={`/modules/${item.module.id}?tab=${tab}`}
          className="block truncate text-sm font-medium hover:underline"
        >
          {item.title}
        </Link>
        <p className="text-muted-foreground flex flex-wrap items-center gap-x-2 text-xs">
          <span className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="size-2 rounded-full"
              style={{ backgroundColor: item.module.colour }}
            />
            {item.module.code}
          </span>
          <span>{item.label}</span>
          <span className={cn(item.overdue && "text-destructive font-medium")}>
            {formatDue(item.dueAt)} · {relativeDay(item.dueAt)}
          </span>
        </p>
      </div>
      {item.overdue && <Badge variant="destructive">Overdue</Badge>}
      {item.overdue && item.type === "assessment" && (
        <Button variant="outline" size="sm" onClick={onDone}>
          Mark completed
        </Button>
      )}
    </li>
  );
}
