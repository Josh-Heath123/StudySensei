import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Pencil, Plus, Trash2 } from "lucide-react";
import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { ConfirmDialog } from "@/ui/confirm-dialog";
import { Input } from "@/ui/input";

import {
  useCreateTopic,
  useDeleteTopic,
  useMoveTopic,
  useRenameTopic,
  useTopicTree,
  type TopicMove,
  type TopicNode,
} from "./api";
import { TopicMapPanel } from "./TopicMapPanel";
import { moveTarget } from "./treeMoves";

function countAi(nodes: TopicNode[]): number {
  return nodes.reduce(
    (sum, node) => sum + (node.source === "ai" ? 1 : 0) + countAi(node.children),
    0,
  );
}

function countDescendants(node: TopicNode): number {
  return node.children.reduce((sum, child) => sum + 1 + countDescendants(child), 0);
}

type Actions = {
  busy: boolean;
  add: (name: string, parentId: string | null) => Promise<void>;
  rename: (topic: TopicNode, name: string) => Promise<void>;
  move: (topic: TopicNode, target: TopicMove) => Promise<void>;
  askDelete: (topic: TopicNode) => void;
};

export function TopicTree({ moduleId }: { moduleId: string }) {
  const tree = useTopicTree(moduleId);
  const createTopic = useCreateTopic(moduleId);
  const renameTopic = useRenameTopic(moduleId);
  const moveTopic = useMoveTopic(moduleId);
  const deleteTopic = useDeleteTopic(moduleId);
  const [error, setError] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<TopicNode | null>(null);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      throw err;
    }
  }

  const actions: Actions = {
    busy: moveTopic.isPending,
    add: (name, parentId) => run(() => createTopic.mutateAsync({ name, parentId })),
    rename: (topic, name) => run(() => renameTopic.mutateAsync({ topicId: topic.id, name })),
    move: (topic, target) => run(() => moveTopic.mutateAsync({ topicId: topic.id, ...target })),
    askDelete: setToDelete,
  };

  const subtopics = toDelete ? countDescendants(toDelete) : 0;

  return (
    <section aria-labelledby="topics-heading" className="max-w-3xl">
      <h2 id="topics-heading" className="type-h3 mb-1">
        Topics
      </h2>
      <p className="text-muted mb-4 text-sm">
        Build the module's topic tree. Use the arrows to reorder, indent and outdent. Topics marked
        AI were suggested from your materials; editing one makes it yours.
      </p>

      <TopicMapPanel moduleId={moduleId} aiTopics={countAi(tree.data ?? [])} />

      {error && (
        <p role="alert" className="text-danger mb-3 text-sm">
          {error}
        </p>
      )}

      {tree.isPending && <p className="text-muted text-sm">Loading topics…</p>}
      {tree.isError && (
        <p role="alert" className="text-danger text-sm">
          Couldn't load topics: {tree.error.message}
        </p>
      )}
      {tree.data?.length === 0 && (
        <p className="text-muted mb-3 text-sm">No topics yet. Add the first one below.</p>
      )}
      {tree.data && tree.data.length > 0 && (
        <TopicList nodes={tree.data} parent={null} actions={actions} label="Topics" />
      )}

      <AddTopicForm
        label="New topic"
        placeholder="Add a topic"
        onAdd={(name) => actions.add(name, null)}
        className="mt-3"
      />

      <ConfirmDialog
        open={toDelete !== null}
        onOpenChange={(open) => !open && setToDelete(null)}
        title={`Delete “${toDelete?.name ?? ""}”?`}
        description={
          subtopics > 0
            ? `This also deletes its ${subtopics} subtopic${subtopics === 1 ? "" : "s"}.`
            : "This can't be undone."
        }
        confirmLabel="Delete topic"
        onConfirm={() => deleteTopic.mutateAsync(toDelete!.id)}
      />
    </section>
  );
}

function TopicList({
  nodes,
  parent,
  actions,
  label,
}: {
  nodes: TopicNode[];
  parent: TopicNode | null;
  actions: Actions;
  label: string;
}) {
  return (
    <ul
      aria-label={label}
      className={parent ? "border-line mt-1 ml-6 border-l-2 pl-3" : "space-y-1"}
    >
      {nodes.map((node, index) => (
        <TopicItem
          key={node.id}
          node={node}
          index={index}
          siblings={nodes}
          parent={parent}
          actions={actions}
        />
      ))}
    </ul>
  );
}

function TopicItem({
  node,
  index,
  siblings,
  parent,
  actions,
}: {
  node: TopicNode;
  index: number;
  siblings: TopicNode[];
  parent: TopicNode | null;
  actions: Actions;
}) {
  const [renaming, setRenaming] = useState(false);
  const [adding, setAdding] = useState(false);

  const moves = [
    { action: "up", label: "Move up", icon: ArrowUp },
    { action: "down", label: "Move down", icon: ArrowDown },
    { action: "outdent", label: "Outdent", icon: ArrowLeft },
    { action: "indent", label: "Indent", icon: ArrowRight },
  ] as const;

  return (
    <li>
      <div className="group hover:bg-surface flex items-center gap-1 rounded-md py-0.5 pr-1 pl-2">
        {renaming ? (
          <RenameInput
            initial={node.name}
            onSave={async (name) => {
              setRenaming(false);
              if (name !== node.name) await actions.rename(node, name);
            }}
            onCancel={() => setRenaming(false)}
          />
        ) : (
          <button
            type="button"
            onClick={() => setRenaming(true)}
            className="min-w-0 flex-1 truncate py-1 text-left text-sm"
            title="Click to rename"
          >
            {node.name}
          </button>
        )}
        {!renaming && (
          <span className="flex shrink-0 items-center gap-2">
            {node.linked_pages > 0 && (
              <span className="text-muted text-xs">
                {node.linked_pages} {node.linked_pages === 1 ? "page" : "pages"}
              </span>
            )}
            {node.source === "ai" && (
              <Badge variant="secondary" title="Suggested by AI from your materials">
                AI
              </Badge>
            )}
          </span>
        )}

        <div className="flex shrink-0 items-center opacity-60 group-focus-within:opacity-100 group-hover:opacity-100">
          {moves.map(({ action, label, icon: Icon }) => {
            const target = moveTarget(action, siblings, index, parent);
            return (
              <Button
                key={action}
                variant="ghost"
                size="icon-sm"
                aria-label={`${label}: ${node.name}`}
                disabled={!target || actions.busy}
                onClick={() => target && actions.move(node, target).catch(() => {})}
              >
                <Icon aria-hidden />
              </Button>
            );
          })}
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Rename: ${node.name}`}
            onClick={() => setRenaming(true)}
          >
            <Pencil aria-hidden />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Add subtopic to: ${node.name}`}
            onClick={() => setAdding(true)}
          >
            <Plus aria-hidden />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Delete: ${node.name}`}
            onClick={() => actions.askDelete(node)}
          >
            <Trash2 aria-hidden />
          </Button>
        </div>
      </div>

      {node.children.length > 0 && (
        <TopicList
          nodes={node.children}
          parent={node}
          actions={actions}
          label={`Subtopics of ${node.name}`}
        />
      )}
      {adding && (
        <AddTopicForm
          label={`New subtopic of ${node.name}`}
          placeholder="Subtopic name"
          autoFocus
          className="mt-1 ml-9"
          onAdd={(name) => actions.add(name, node.id)}
          onDone={() => setAdding(false)}
        />
      )}
    </li>
  );
}

function RenameInput({
  initial,
  onSave,
  onCancel,
}: {
  initial: string;
  onSave: (name: string) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial);
  // Enter/Escape unmount the input, and some browsers then fire blur on it;
  // only the first of those may act, or Escape could still save.
  const done = useRef(false);

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      save();
    } else if (event.key === "Escape") {
      event.preventDefault();
      done.current = true;
      onCancel();
    }
  }

  function save() {
    if (done.current) return;
    done.current = true;
    const trimmed = name.trim();
    if (trimmed) onSave(trimmed).catch(() => {});
    else onCancel();
  }

  return (
    <Input
      aria-label={`Rename ${initial}`}
      value={name}
      autoFocus
      onChange={(e) => setName(e.target.value)}
      onKeyDown={onKeyDown}
      onBlur={save}
      className="flex-1"
      maxLength={200}
    />
  );
}

function AddTopicForm({
  label,
  placeholder,
  onAdd,
  onDone,
  autoFocus,
  className,
}: {
  label: string;
  placeholder: string;
  onAdd: (name: string) => Promise<void>;
  onDone?: () => void;
  autoFocus?: boolean;
  className?: string;
}) {
  const [name, setName] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    try {
      await onAdd(trimmed);
      setName("");
    } catch {
      // The tree shows the error; keep the text so it can be retried.
    }
  }

  return (
    <form onSubmit={submit} className={`flex gap-2 ${className ?? ""}`}>
      <Input
        aria-label={label}
        placeholder={placeholder}
        value={name}
        autoFocus={autoFocus}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => e.key === "Escape" && onDone?.()}
        maxLength={200}
        className="max-w-sm"
      />
      <Button type="submit" size="sm" variant="secondary" disabled={!name.trim()}>
        Add
      </Button>
      {onDone && (
        <Button type="button" size="sm" variant="ghost" onClick={onDone}>
          Done
        </Button>
      )}
    </form>
  );
}
