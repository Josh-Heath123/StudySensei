import { MoreHorizontal, Plus } from "lucide-react";
import { useId, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { PageHeader } from "@/app/PageHeader";
import { useModules, useTopicTree } from "@/features/modules/api";
import { useNow } from "@/lib/useNow";
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { ConfirmDialog } from "@/ui/confirm-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/ui/dropdown-menu";
import { Label } from "@/ui/label";
import { NativeSelect } from "@/ui/native-select";

import {
  useDeleteItem,
  useItems,
  useUpdateItem,
  type ItemFilters,
  type PracticeItem,
  type RejectReason,
} from "./api";
import { ItemDialog } from "./ItemDialog";
import { flattenTopics, memoryText, plural } from "./practiceText";
import { SourceChips } from "./SourceChips";

const STATUSES = [
  ["active", "Active"],
  ["suspended", "Suspended"],
  ["rejected", "Rejected"],
] as const;
const ORIGINS = [
  ["ai", "AI"],
  ["user", "Yours"],
] as const;
const KINDS = [
  ["flashcard", "Flashcard"],
  ["short_answer", "Short answer"],
] as const;
const REASONS: [RejectReason, string][] = [
  ["wrong", "It's wrong"],
  ["unclear", "It's unclear"],
  ["not_in_source", "It isn't in the source"],
  ["duplicate", "It repeats another card"],
  ["other", "Something else"],
];

/**
 * Every practice item (/practice/items?module=&topic=), filtered by topic, status, origin
 * and kind, with its memory state and the actions on it.
 */
export function ItemsPage() {
  const [params, setParams] = useSearchParams();
  const filters: ItemFilters = {
    moduleId: params.get("module") ?? undefined,
    topicId: params.get("topic") ?? undefined,
    status: (params.get("status") as ItemFilters["status"]) ?? undefined,
    origin: (params.get("origin") as ItemFilters["origin"]) ?? undefined,
    kind: (params.get("kind") as ItemFilters["kind"]) ?? undefined,
  };
  const modules = useModules();
  const tree = useTopicTree(filters.moduleId ?? "", filters.moduleId !== undefined);
  const items = useItems(filters);
  const [adding, setAdding] = useState(false);
  const [message, setMessage] = useState("");
  const id = useId();

  function set(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    if (name === "module") next.delete("topic");
    setParams(next);
  }

  const filtersUi: [string, string, string, readonly (readonly [string, string])[]][] = [
    ["status", "Status", "Any status", STATUSES],
    ["origin", "Origin", "AI or yours", ORIGINS],
    ["kind", "Kind", "Any kind", KINDS],
  ];

  return (
    <>
      <PageHeader
        eyebrow={
          <Link to="/practice" className="hover:underline">
            Practice
          </Link>
        }
        title="Items"
        aside={
          <Button variant="outline" onClick={() => setAdding(true)}>
            <Plus aria-hidden />
            Add a card
          </Button>
        }
      />
      <section aria-label="Filters" className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <div className="grid gap-1.5">
          <Label htmlFor={`${id}-module`}>Module</Label>
          <NativeSelect
            id={`${id}-module`}
            value={filters.moduleId ?? ""}
            onChange={(event) => set("module", event.target.value)}
          >
            <option value="">All modules</option>
            {modules.data?.map((m) => (
              <option key={m.id} value={m.id}>
                {m.code} {m.name}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor={`${id}-topic`}>Topic</Label>
          <NativeSelect
            id={`${id}-topic`}
            value={filters.topicId ?? ""}
            disabled={!filters.moduleId}
            onChange={(event) => set("topic", event.target.value)}
          >
            <option value="">{filters.moduleId ? "Every topic" : "Choose a module first"}</option>
            {flattenTopics(tree.data ?? []).map((t) => (
              <option key={t.id} value={t.id}>
                {" ".repeat(t.depth * 2)}
                {t.name}
              </option>
            ))}
          </NativeSelect>
        </div>
        {filtersUi.map(([name, label, any, options]) => (
          <div key={name} className="grid gap-1.5">
            <Label htmlFor={`${id}-${name}`}>{label}</Label>
            <NativeSelect
              id={`${id}-${name}`}
              value={params.get(name) ?? ""}
              onChange={(event) => set(name, event.target.value)}
            >
              <option value="">{any}</option>
              {options.map(([value, text]) => (
                <option key={value} value={value}>
                  {text}
                </option>
              ))}
            </NativeSelect>
          </div>
        ))}
      </section>
      <p aria-live="polite" className="text-success mb-3 text-sm empty:hidden">
        {message}
      </p>
      {items.isError ? (
        <p role="alert" className="text-danger">
          Couldn&apos;t load the items: {items.error.message}
        </p>
      ) : !items.data ? (
        <div aria-busy="true" className="grid gap-3">
          <p className="sr-only">Loading…</p>
          {[0, 1, 2].map((n) => (
            <div key={n} className="skeleton h-20 rounded-lg" />
          ))}
        </div>
      ) : items.data.items.length === 0 ? (
        <p className="text-muted">No items match. Add a card, or generate practice for a topic.</p>
      ) : (
        <>
          <p className="text-muted mb-3 text-sm">
            {items.data.total > items.data.items.length
              ? `The newest ${items.data.items.length} of ${items.data.total} items.`
              : plural(items.data.total, "item")}
          </p>
          <ul aria-label="Items" className="grid gap-3">
            {items.data.items.map((item) => (
              <ItemRow key={item.id} item={item} onDone={setMessage} />
            ))}
          </ul>
        </>
      )}
      {adding && (
        <ItemDialog
          moduleId={filters.moduleId}
          topicId={filters.topicId}
          onClose={() => setAdding(false)}
          onSaved={setMessage}
        />
      )}
    </>
  );
}

function ItemRow({ item, onDone }: { item: PracticeItem; onDone: (message: string) => void }) {
  const now = useNow();
  const update = useUpdateItem();
  const remove = useDeleteItem();
  const [editing, setEditing] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const short = item.prompt.length > 90 ? `${item.prompt.slice(0, 87)}…` : item.prompt;

  async function setStatus(status: "active" | "suspended") {
    try {
      await update.mutateAsync({ itemId: item.id, status });
      onDone(
        status === "active"
          ? "Restored: it's back in your reviews."
          : "Suspended: it's left out of reviews.",
      );
    } catch {
      // Shown in the row.
    }
  }

  return (
    <li className="surface-card grid gap-2 rounded-lg p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="grid min-w-0 gap-1.5">
          <p className="font-semibold [overflow-wrap:anywhere]">{item.prompt}</p>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge variant="secondary">
              {item.kind === "short_answer" ? "Short answer" : "Flashcard"}
            </Badge>
            <Badge variant="outline">{item.origin === "ai" ? "AI" : "Yours"}</Badge>
            {item.status !== "active" && (
              <Badge variant={item.status === "rejected" ? "destructive" : "warning"}>
                {item.status === "rejected" ? "Rejected" : "Suspended"}
              </Badge>
            )}
            <span className="text-muted">{memoryText(item.memory, now)}</span>
          </div>
          <SourceChips item={item} />
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon-sm" aria-label={`Actions for "${short}"`}>
              <MoreHorizontal aria-hidden />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => setEditing(true)}>Edit</DropdownMenuItem>
            {item.status === "active" ? (
              <DropdownMenuItem onSelect={() => void setStatus("suspended")}>
                Suspend
              </DropdownMenuItem>
            ) : (
              <DropdownMenuItem onSelect={() => void setStatus("active")}>Restore</DropdownMenuItem>
            )}
            {item.origin === "ai" && item.status !== "rejected" && (
              <DropdownMenuItem onSelect={() => setRejecting(true)}>Reject…</DropdownMenuItem>
            )}
            <DropdownMenuItem destructive onSelect={() => setDeleting(true)}>
              Delete…
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {update.isError && (
        <p role="alert" className="text-danger text-sm">
          {update.error.message}
        </p>
      )}
      {editing && <ItemDialog item={item} onClose={() => setEditing(false)} onSaved={onDone} />}
      {rejecting && (
        <RejectDialog item={item} onClose={() => setRejecting(false)} onDone={onDone} />
      )}
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title="Delete this card?"
        description="It and its review history are deleted for good. To keep the history, suspend it instead."
        confirmLabel="Delete"
        onConfirm={async () => {
          await remove.mutateAsync(item.id);
          onDone("Card deleted.");
        }}
      />
    </li>
  );
}

function RejectDialog({
  item,
  onClose,
  onDone,
}: {
  item: PracticeItem;
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const update = useUpdateItem();
  const [reason, setReason] = useState<RejectReason>("wrong");
  const id = useId();
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Reject this card?</DialogTitle>
          <DialogDescription>
            It leaves your reviews and mastery, and the reason helps judge the AI&apos;s cards.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-1.5">
          <Label htmlFor={id}>Why?</Label>
          <NativeSelect
            id={id}
            value={reason}
            onChange={(event) => setReason(event.target.value as RejectReason)}
          >
            {REASONS.map(([value, text]) => (
              <option key={value} value={value}>
                {text}
              </option>
            ))}
          </NativeSelect>
        </div>
        {update.isError && (
          <p role="alert" className="text-danger text-sm">
            {update.error.message}
          </p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={update.isPending}
            onClick={() =>
              void update
                .mutateAsync({ itemId: item.id, status: "rejected", reject_reason: reason })
                .then(() => {
                  onDone("Card rejected.");
                  onClose();
                })
                .catch(() => undefined)
            }
          >
            Reject
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
