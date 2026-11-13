import { Trash2, Upload, X } from "lucide-react";
import { useId, useRef, useState, type DragEvent } from "react";

import { cn } from "@/lib/utils";
import { Button } from "@/ui/button";
import { ConfirmDialog } from "@/ui/confirm-dialog";
import { Input } from "@/ui/input";
import { Label } from "@/ui/label";
import { NativeSelect } from "@/ui/native-select";

import {
  useDeleteMaterial,
  useMaterials,
  useRetryMaterial,
  useUpdateMaterial,
  useUploadMaterial,
  type Material,
} from "./api";
import {
  ACCEPT,
  checkFile,
  formatSize,
  guessKind,
  KIND_LABELS,
  KINDS,
  titleFrom,
  type MaterialKind,
} from "./kinds";

type Staged = {
  key: string;
  file: File;
  kind: MaterialKind;
  title: string;
  allowAi: boolean;
  state: "waiting" | "uploading" | "failed";
  error?: string;
};

let nextKey = 0;

/** Upload a module's slides, notes and papers, and follow their processing. */
export function MaterialsTab({ moduleId }: { moduleId: string }) {
  const materials = useMaterials(moduleId);
  const upload = useUploadMaterial(moduleId);
  const [staged, setStaged] = useState<Staged[]>([]);
  const [refused, setRefused] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  function add(files: FileList | File[]) {
    const accepted: Staged[] = [];
    const problems: string[] = [];
    for (const file of Array.from(files)) {
      const problem = checkFile(file);
      if (problem) problems.push(problem);
      else
        accepted.push({
          key: String(nextKey++),
          file,
          kind: guessKind(file.name),
          title: titleFrom(file.name),
          allowAi: true,
          state: "waiting",
        });
    }
    setRefused(problems);
    setStaged((current) => [...current, ...accepted]);
  }

  const change = (key: string, patch: Partial<Staged>) =>
    setStaged((current) => current.map((s) => (s.key === key ? { ...s, ...patch } : s)));

  async function uploadAll() {
    setBusy(true);
    // One at a time: each is up to 50 MB, and each result is shown on its own row.
    for (const item of staged) {
      change(item.key, { state: "uploading", error: undefined });
      try {
        await upload.mutateAsync(item);
        setStaged((current) => current.filter((s) => s.key !== item.key));
      } catch (error) {
        change(item.key, { state: "failed", error: (error as Error).message });
      }
    }
    setBusy(false);
  }

  const rows = materials.data ?? [];

  return (
    <section aria-labelledby="materials-heading" className="max-w-3xl">
      <h2 id="materials-heading" className="type-h3 mb-4">
        Materials
      </h2>

      <DropZone onFiles={add} disabled={busy} />
      {refused.length > 0 && (
        <ul role="alert" className="text-danger mt-3 grid gap-1 text-sm">
          {refused.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      )}

      {staged.length > 0 && (
        <div className="mt-6">
          <ul aria-label="Files to upload" className="divide-line border-line divide-y border-y">
            {staged.map((item) => (
              <StagedRow
                key={item.key}
                item={item}
                disabled={busy}
                onChange={(patch) => change(item.key, patch)}
                onRemove={() => setStaged((current) => current.filter((s) => s.key !== item.key))}
              />
            ))}
          </ul>
          <Button className="mt-4" disabled={busy} onClick={() => void uploadAll()}>
            <Upload aria-hidden />
            {busy
              ? "Uploading…"
              : `Upload ${staged.length} ${staged.length === 1 ? "file" : "files"}`}
          </Button>
        </div>
      )}

      <div className="mt-8">
        {materials.isPending && <p className="text-muted text-sm">Loading…</p>}
        {materials.isError && (
          <p role="alert" className="text-danger text-sm">
            {materials.error.message}
          </p>
        )}
        {materials.isSuccess && rows.length === 0 && staged.length === 0 && (
          <p className="text-muted border-line rounded-lg border-2 p-6">
            No materials yet. Drop slides, notes or past papers above.
          </p>
        )}
        {rows.length > 0 && (
          <ul aria-label="Materials" className="divide-line border-line divide-y border-y">
            {rows.map((material) => (
              <MaterialRow key={material.id} material={material} moduleId={moduleId} />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function DropZone({
  onFiles,
  disabled,
}: {
  onFiles: (files: FileList) => void;
  disabled: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const inputId = useId();

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setOver(false);
    if (!disabled && event.dataTransfer.files.length > 0) onFiles(event.dataTransfer.files);
  };

  return (
    <div
      data-testid="drop-zone"
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      className={cn(
        "grid justify-items-start gap-3 rounded-lg border-2 border-dashed p-6",
        over ? "border-ink bg-surface" : "border-line",
      )}
    >
      <p>
        <strong>Drop files here</strong>{" "}
        <span className="text-muted">
          or choose them. PDF, PPTX, DOCX, MD, TXT, PNG or JPG, up to 50 MB each.
        </span>
      </p>
      <Button variant="outline" disabled={disabled} onClick={() => input.current?.click()}>
        Choose files
      </Button>
      <label htmlFor={inputId} className="sr-only">
        Files to upload
      </label>
      <input
        ref={input}
        id={inputId}
        type="file"
        multiple
        accept={ACCEPT}
        className="sr-only"
        tabIndex={-1}
        onChange={(event) => {
          if (event.target.files?.length) onFiles(event.target.files);
          event.target.value = ""; // so choosing the same file again still fires
        }}
      />
    </div>
  );
}

function StagedRow({
  item,
  disabled,
  onChange,
  onRemove,
}: {
  item: Staged;
  disabled: boolean;
  onChange: (patch: Partial<Staged>) => void;
  onRemove: () => void;
}) {
  const id = useId();
  return (
    <li className="grid gap-3 py-4" aria-label={item.file.name}>
      <div className="flex items-center justify-between gap-3">
        <p className="min-w-0 truncate text-sm font-medium">
          {item.file.name}{" "}
          <span className="text-muted font-normal">{formatSize(item.file.size)}</span>
        </p>
        <Button
          variant="ghost"
          size="icon-sm"
          disabled={disabled}
          onClick={onRemove}
          aria-label={`Remove ${item.file.name}`}
        >
          <X aria-hidden />
        </Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-[2fr_1fr]">
        <div className="grid gap-1">
          <Label htmlFor={`${id}-title`}>Title</Label>
          <Input
            id={`${id}-title`}
            value={item.title}
            maxLength={200}
            disabled={disabled}
            onChange={(event) => onChange({ title: event.target.value })}
          />
        </div>
        <div className="grid gap-1">
          <Label htmlFor={`${id}-kind`}>Kind</Label>
          <NativeSelect
            id={`${id}-kind`}
            value={item.kind}
            disabled={disabled}
            onChange={(event) => onChange({ kind: event.target.value as MaterialKind })}
          >
            {KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {KIND_LABELS[kind]}
              </option>
            ))}
          </NativeSelect>
        </div>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          className="accent-ink size-5"
          checked={item.allowAi}
          disabled={disabled}
          onChange={(event) => onChange({ allowAi: event.target.checked })}
        />
        Allow AI processing
      </label>
      {item.state === "uploading" && <p className="text-muted text-sm">Uploading…</p>}
      {item.state === "failed" && (
        <p role="alert" className="text-danger text-sm">
          Not uploaded: {item.error}
        </p>
      )}
    </li>
  );
}

function statusText(material: Material): { text: string; tone: "muted" | "ink" | "danger" } {
  if (material.status === "failed") return { text: `Failed: ${material.error}`, tone: "danger" };
  if (material.retrying) return { text: `Retrying: ${material.error}`, tone: "muted" };
  if (material.status === "ready") return { text: "Ready", tone: "ink" };
  if (material.status === "processing") return { text: "Processing…", tone: "muted" };
  return { text: "Waiting to be processed…", tone: "muted" };
}

function MaterialRow({ material, moduleId }: { material: Material; moduleId: string }) {
  const update = useUpdateMaterial(moduleId);
  const retry = useRetryMaterial(moduleId);
  const remove = useDeleteMaterial(moduleId);
  const [deleting, setDeleting] = useState(false);
  const status = statusText(material);
  const details = [
    KIND_LABELS[material.kind],
    material.original_filename,
    formatSize(material.size_bytes),
    material.page_count !== null
      ? `${material.page_count} ${material.page_count === 1 ? "page" : "pages"}`
      : null,
  ].filter(Boolean);

  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3" aria-label={material.title}>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{material.title}</p>
        <p className="text-muted flex flex-wrap gap-x-3 text-xs">
          {details.map((detail) => (
            <span key={detail}>{detail}</span>
          ))}
        </p>
        <p
          role="status"
          className={cn(
            "mt-1 text-xs font-semibold",
            status.tone === "danger" && "text-danger",
            status.tone === "muted" && "text-muted",
          )}
        >
          {status.text}
        </p>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          className="accent-ink size-5"
          checked={material.allow_ai}
          disabled={update.isPending}
          onChange={(event) =>
            update.mutate({ id: material.id, changes: { allow_ai: event.target.checked } })
          }
        />
        Allow AI
      </label>
      {material.status === "failed" && (
        <Button
          variant="outline"
          size="sm"
          disabled={retry.isPending}
          onClick={() => retry.mutate(material.id)}
        >
          Retry
        </Button>
      )}
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={() => setDeleting(true)}
        aria-label={`Delete ${material.title}`}
      >
        <Trash2 aria-hidden />
      </Button>
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Delete ${material.title}?`}
        description="The file is deleted too, unless another of your modules has the same file."
        confirmLabel="Delete material"
        onConfirm={() => remove.mutateAsync(material.id)}
      />
    </li>
  );
}
