import { Link } from "react-router";

/**
 * One slim, solid card under the timer: where the module's materials live (its Materials
 * tab: upload, search and the page viewer). The tutor has its own panel (TutorDock).
 */
export function SessionNotes({ moduleId }: { moduleId: string }) {
  return (
    <div className="surface-card divide-line grid w-full divide-y rounded-xl px-5 text-sm sm:px-6">
      <section aria-labelledby="materials-heading" className="grid gap-1 py-4">
        <h2 id="materials-heading" className="type-label text-muted">
          Materials
        </h2>
        <p>
          Open this module&apos;s slides and notes, search them, and jump to any page.{" "}
          <Link
            to={`/modules/${moduleId}`}
            className="text-link font-semibold underline-offset-4 hover:underline"
          >
            Open module
          </Link>
        </p>
      </section>
    </div>
  );
}
