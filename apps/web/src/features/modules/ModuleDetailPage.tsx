import { ArrowLeft, Pencil, Trash2 } from "lucide-react";
import { useState, type CSSProperties } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import { PageHeader } from "@/app/PageHeader";
import { ApiError } from "@/lib/api/errors";
import { ConfirmDialog } from "@/ui/confirm-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  MoreButton,
} from "@/ui/dropdown-menu";
import { ModuleBadge } from "@/ui/module-badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/ui/tabs";

import { useDeleteModule, useModule, useUpdateModule } from "./api";
import { StartSessionButton } from "../session/StartSessionButton";
import { ModuleForm } from "./ModuleForm";
import { AssessmentsTab } from "./assessments/AssessmentsTab";
import { MaterialsTab } from "./materials/MaterialsTab";
import { SessionsTab } from "./sessions/SessionsTab";
import { TasksTab } from "./tasks/TasksTab";
import { LoadingRows } from "./LoadingRows";
import { TopicTree } from "./TopicTree";

export function ModuleDetailPage() {
  const { moduleId = "" } = useParams();
  const navigate = useNavigate();
  const module = useModule(moduleId);
  const updateModule = useUpdateModule(moduleId);
  const deleteModule = useDeleteModule(moduleId);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const backLink = (
    <Link
      to="/modules"
      className="text-muted hover:text-fg mb-6 inline-flex min-h-9 items-center gap-1.5 rounded-md text-sm font-semibold transition-colors"
    >
      <ArrowLeft className="size-4" aria-hidden /> All modules
    </Link>
  );

  if (module.isPending) {
    return (
      <div className="grid gap-6">
        {backLink}
        <LoadingRows label="Loading module…" rows={1} rowClassName="h-20 max-w-xl" />
        <div aria-hidden className="skeleton h-12 max-w-2xl" />
      </div>
    );
  }
  if (module.isError) {
    const missing = module.error instanceof ApiError && module.error.status === 404;
    return (
      <>
        {backLink}
        <p role="alert" className="text-danger text-sm">
          {missing ? "This module doesn't exist (it may have been deleted)." : module.error.message}
        </p>
      </>
    );
  }

  const data = module.data;
  // Components on this page take the module's colour from --module.
  return (
    <div style={{ "--module": data.colour } as CSSProperties}>
      {backLink}
      {/* The module's colour as a thin accent above the header, not a heavy block. */}
      <div aria-hidden className="mb-5 h-1 w-14 rounded-xs bg-[var(--module)]" />
      <PageHeader
        eyebrow={
          <span className="flex flex-wrap items-center gap-3 normal-case">
            <ModuleBadge>{data.code}</ModuleBadge>
            {data.semester && <span className="type-label">{data.semester}</span>}
          </span>
        }
        title={data.name}
        aside={
          <>
            <StartSessionButton moduleId={data.id} />
            {/* Start session is the one primary action; the rest wait in the menu. */}
            <DropdownMenu>
              <MoreButton label="Module actions" className="size-11" />
              <DropdownMenuContent>
                <DropdownMenuItem onSelect={() => setEditing(true)}>
                  <Pencil aria-hidden /> Edit
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem destructive onSelect={() => setDeleting(true)}>
                  <Trash2 aria-hidden /> Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        }
      />

      <ModuleTabs moduleId={moduleId} />

      <Dialog open={editing} onOpenChange={setEditing}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit {data.code}</DialogTitle>
          </DialogHeader>
          <ModuleForm
            initial={data}
            submitLabel="Save changes"
            onCancel={() => setEditing(false)}
            onSubmit={async (values) => {
              await updateModule.mutateAsync(values);
              setEditing(false);
            }}
          />
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Delete ${data.code}?`}
        description="This also deletes all of its topics, assessments and tasks. It can't be undone."
        confirmLabel="Delete module"
        onConfirm={async () => {
          await deleteModule.mutateAsync();
          navigate("/modules");
        }}
      />
    </div>
  );
}

// The first tab is the default. The open tab lives in ?tab= so reloads and links keep it.
const TABS = [
  { value: "assessments", label: "Assessments", Panel: AssessmentsTab },
  { value: "tasks", label: "Tasks", Panel: TasksTab },
  { value: "topics", label: "Topics", Panel: TopicTree },
  { value: "materials", label: "Materials", Panel: MaterialsTab },
  { value: "sessions", label: "Sessions", Panel: SessionsTab },
];

function ModuleTabs({ moduleId }: { moduleId: string }) {
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab");
  const current = TABS.some((t) => t.value === requested) ? requested! : TABS[0]!.value;

  return (
    <Tabs
      value={current}
      onValueChange={(tab) => setParams({ tab }, { replace: true })}
      className="mt-2"
    >
      <TabsList className="sm:w-fit">
        {TABS.map(({ value, label }) => (
          <TabsTrigger key={value} value={value}>
            {label}
          </TabsTrigger>
        ))}
      </TabsList>
      {TABS.map(({ value, Panel }) => (
        <TabsContent key={value} value={value} className="pt-8">
          <Panel moduleId={moduleId} />
        </TabsContent>
      ))}
    </Tabs>
  );
}
