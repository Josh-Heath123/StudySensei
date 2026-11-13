import { Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { PageHeader } from "@/app/PageHeader";
import { Button } from "@/ui/button";
import { Card, CardContent } from "@/ui/card";
import { ModuleBadge } from "@/ui/module-badge";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/ui/dialog";

import { useCreateModule, useModules, type Module } from "./api";
import { ModuleForm } from "./ModuleForm";

export function ModulesPage() {
  const modules = useModules();
  const createModule = useCreateModule();
  const [creating, setCreating] = useState(false);

  return (
    <>
      <PageHeader
        title="Modules"
        description="The subjects you're studying this semester."
        aside={
          <Button onClick={() => setCreating(true)}>
            <Plus aria-hidden /> New module
          </Button>
        }
      />

      {modules.isPending && <p className="text-muted text-sm">Loading modules…</p>}
      {modules.isError && (
        <p role="alert" className="text-danger text-sm">
          Couldn't load modules: {modules.error.message}
        </p>
      )}
      {modules.data?.length === 0 && (
        <Card className="max-w-md">
          <CardContent className="grid gap-3">
            <p className="font-semibold">No modules yet</p>
            <p className="text-muted text-sm">
              Add each module you're taking. Topics, assessments and study plans hang off them.
            </p>
            <Button className="justify-self-start" onClick={() => setCreating(true)}>
              Add your first module
            </Button>
          </CardContent>
        </Card>
      )}
      {modules.data && modules.data.length > 0 && (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {modules.data.map((module) => (
            <li key={module.id}>
              <ModuleCard module={module} />
            </li>
          ))}
        </ul>
      )}

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New module</DialogTitle>
            <DialogDescription>You can add topics once it's created.</DialogDescription>
          </DialogHeader>
          <ModuleForm
            submitLabel="Create module"
            onCancel={() => setCreating(false)}
            onSubmit={async (values) => {
              await createModule.mutateAsync(values);
              setCreating(false);
            }}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}

function ModuleCard({ module }: { module: Module }) {
  return (
    <Link
      to={`/modules/${module.id}`}
      aria-label={[`${module.code}: ${module.name}`, module.semester].filter(Boolean).join(", ")}
      className="bg-paper border-line hover:border-ink flex h-full flex-col items-start gap-3 rounded-lg border-2 p-5 transition-colors"
    >
      <ModuleBadge colour={module.colour}>{module.code}</ModuleBadge>
      <span className="type-h3 max-w-full truncate">{module.name}</span>
      {module.semester && <span className="text-muted text-sm">{module.semester}</span>}
    </Link>
  );
}
