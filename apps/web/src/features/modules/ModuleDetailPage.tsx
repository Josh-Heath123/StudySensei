import { ArrowLeft, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { PageHeader } from "@/app/PageHeader";
import { ApiError } from "@/lib/api/errors";
import { Button } from "@/ui/button";
import { ConfirmDialog } from "@/ui/confirm-dialog";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/ui/dialog";

import { useDeleteModule, useModule, useUpdateModule } from "./api";
import { ModuleForm } from "./ModuleForm";
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
      className="text-muted-foreground hover:text-foreground mb-4 inline-flex items-center gap-1 text-sm"
    >
      <ArrowLeft className="size-4" aria-hidden /> All modules
    </Link>
  );

  if (module.isPending) {
    return <p className="text-muted-foreground text-sm">Loading…</p>;
  }
  if (module.isError) {
    const missing = module.error instanceof ApiError && module.error.status === 404;
    return (
      <>
        {backLink}
        <p role="alert" className="text-destructive text-sm">
          {missing ? "This module doesn't exist (it may have been deleted)." : module.error.message}
        </p>
      </>
    );
  }

  const data = module.data;
  return (
    <>
      {backLink}
      <PageHeader
        title={
          <span className="flex items-center gap-3">
            <span
              aria-hidden
              className="size-3.5 rounded-full"
              style={{ backgroundColor: data.colour }}
            />
            {data.code}
          </span>
        }
        description={[data.name, data.semester].filter(Boolean).join(" · ")}
        actions={
          <>
            <Button variant="outline" onClick={() => setEditing(true)}>
              <Pencil aria-hidden /> Edit
            </Button>
            <Button variant="outline" onClick={() => setDeleting(true)}>
              <Trash2 aria-hidden /> Delete
            </Button>
          </>
        }
      />

      <TopicTree moduleId={moduleId} />

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
    </>
  );
}
