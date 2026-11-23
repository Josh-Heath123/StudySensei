import { Link } from "react-router";

import { useItems } from "./api";
import { GenerateButton } from "./GenerateButton";
import { plural } from "./practiceText";

/** In the topic dialog: the topic's practice items (subtopics included) and Generate practice. */
export function TopicPractice({
  moduleId,
  topic,
}: {
  moduleId: string;
  topic: { id: string; name: string };
}) {
  const items = useItems({ moduleId, topicId: topic.id });
  const total = items.data?.total;
  return (
    <section aria-label="Practice" className="surface-card grid gap-3 rounded-lg p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="type-label">Practice</h3>
        <Link
          to={`/practice/items?module=${moduleId}&topic=${topic.id}`}
          className="text-link text-sm hover:underline"
        >
          {total === undefined ? "Practice items" : plural(total, "practice item")}
        </Link>
      </div>
      <GenerateButton topicId={topic.id} topicName={topic.name} />
      <p className="text-muted text-xs">
        Written by the AI from this topic&apos;s slides and notes that allow AI, each citing its
        page.
      </p>
    </section>
  );
}
