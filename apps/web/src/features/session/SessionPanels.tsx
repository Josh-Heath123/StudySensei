import { Link } from "react-router";

import { Card, CardContent, CardHeader, CardTitle } from "@/ui/card";

/** Materials come with Phase 2; until then, say so honestly. */
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
          Materials arrive in Phase 2, when you can upload slides and notes.
        </p>
        <Link
          to={`/modules/${moduleId}`}
          className="justify-self-start text-sm font-semibold underline underline-offset-4"
        >
          Open module
        </Link>
      </CardContent>
    </Card>
  );
}

/** docs/DESIGN.md: the tutor panel (2 px ink border). An honest placeholder until Phase 3. */
export function TutorPlaceholder() {
  return (
    <section aria-labelledby="tutor-heading" className="border-ink rounded-lg border-2 p-6">
      <h2 id="tutor-heading" className="type-h3 mb-2">
        Tutor
      </h2>
      <p className="text-muted">The tutor arrives in Phase 3.</p>
    </section>
  );
}
