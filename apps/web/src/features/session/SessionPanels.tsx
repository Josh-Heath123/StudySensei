import { Link } from "react-router";

import { Card, CardContent, CardHeader, CardTitle } from "@/ui/card";

/** The module's materials live on its Materials tab: upload, search and the page viewer. */
export function MaterialsCard({ moduleId }: { moduleId: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Materials</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-2">
        <p className="text-muted">
          Open this module&apos;s slides and notes, search them, and jump to any page.
        </p>
        <Link
          to={`/modules/${moduleId}`}
          className="text-link justify-self-start text-sm font-semibold underline-offset-4 hover:underline"
        >
          Open module
        </Link>
      </CardContent>
    </Card>
  );
}

/** The tutor panel: a solid, calm card. An honest placeholder until Phase 3. */
export function TutorPlaceholder() {
  return (
    <section aria-labelledby="tutor-heading" className="surface-card rounded-xl p-5 sm:p-6">
      <h2 id="tutor-heading" className="type-h3 mb-2">
        Tutor
      </h2>
      <p className="text-muted">The tutor arrives in Phase 3.</p>
    </section>
  );
}
