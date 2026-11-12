import { Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { PageHeader } from "@/app/PageHeader";
import { Button } from "@/ui/button";
import { Card, CardContent } from "@/ui/card";
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
        actions={
          <Button onClick={() => setCreating(true)}>
            <Plus aria-hidden /> New module
          </Button>
        }
      />

      {modules.isPending && <p className="text-muted-foreground text-sm">Loading modules…</p>}
      {modules.isError && (
        <p role="alert" className="text-destructive text-sm">
          Couldn't load modules: {modules.error.message}
        </p>
      )}
      {modules.data?.length === 0 && (
        <Card className="max-w-md">
          <CardContent className="grid gap-3">
            <p className="font-medium">No modules yet</p>
            <p className="text-muted-foreground text-sm">
              Add each module you're taking. Topics, assessments and study plans hang off them.
            </p>
            <Button className="justify-self-start" onClick={() => setCreating(true)}>
              Add your first module
            </Button>
          </CardContent>
        </Card>
      )}
      {modules.data && modules.data.length > 0 && (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
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
      className="bg-card hover:border-primary/50 focus-visible:ring-ring flex items-center gap-3 rounded-xl border p-4 shadow-sm transition-colors focus-visible:ring-2 focus-visible:outline-none"
    >
      <span
        aria-hidden
        className="size-3 shrink-0 rounded-full"
        style={{ backgroundColor: module.colour }}
      />
      <span className="min-w-0">
        <span className="block font-semibold tracking-tight">{module.code}</span>
        <span className="text-muted-foreground block truncate text-sm">{module.name}</span>
      </span>
      {module.semester && (
        <span className="text-muted-foreground ml-auto text-xs">{module.semester}</span>
      )}
    </Link>
  );
}
