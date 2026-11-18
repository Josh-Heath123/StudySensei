import { BookOpen, Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { PageHeader } from "@/app/PageHeader";
import { Button } from "@/ui/button";
import { ModuleBadge } from "@/ui/module-badge";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/ui/dialog";

import { useCreateModule, useModules, type Module } from "./api";
import { EmptyState } from "./EmptyState";
import { LoadingRows } from "./LoadingRows";
import { ModuleForm } from "./ModuleForm";

export function ModulesPage() {
  const modules = useModules();
  const createModule = useCreateModule();
  const [creating, setCreating] = useState(false);
  // One primary action per screen: with no modules yet, it's the empty state's.
  const empty = modules.data?.length === 0;

  return (
    <>
      <PageHeader
        title="Modules"
        description="The subjects you're studying this semester."
        aside={
          <Button variant={empty ? "outline" : "default"} onClick={() => setCreating(true)}>
            <Plus aria-hidden /> New module
          </Button>
        }
      />

      {modules.isPending && (
        <LoadingRows
          label="Loading modules…"
          className="gap-4 sm:grid-cols-2 xl:grid-cols-3"
          rowClassName="h-36 rounded-xl"
        />
      )}
      {modules.isError && (
        <p role="alert" className="text-danger text-sm">
          Couldn't load modules: {modules.error.message}
        </p>
      )}
      {empty && (
        <EmptyState
          icon={BookOpen}
          title="No modules yet"
          className="max-w-2xl"
          action={<Button onClick={() => setCreating(true)}>Add your first module</Button>}
        >
          Add each module you're taking. Topics, assessments and study plans hang off them.
        </EmptyState>
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
      className="surface-card ease-soft relative flex h-full min-h-36 flex-col items-start gap-3 overflow-hidden rounded-xl p-6 pt-7 transition-shadow duration-200 hover:shadow-md"
    >
      {/* The module's colour as a thin edge along the top: an accent, not a block. */}
      <span
        aria-hidden
        className="absolute inset-x-0 top-0 h-1"
        style={{ backgroundColor: module.colour }}
      />
      <ModuleBadge colour={module.colour}>{module.code}</ModuleBadge>
      <span className="type-h3 max-w-full truncate">{module.name}</span>
      {module.semester && <span className="type-label text-muted mt-auto">{module.semester}</span>}
    </Link>
  );
}
