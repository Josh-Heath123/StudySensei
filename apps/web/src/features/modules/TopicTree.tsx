import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Check,
  GitMerge,
  ListTree,
  Pencil,
  Plus,
  Trash2,
  X,
  type LucideIcon,
} from "lucide-react";
import { Fragment, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { cn } from "@/lib/utils";
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { ConfirmDialog } from "@/ui/confirm-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  MoreButton,
} from "@/ui/dropdown-menu";
import { Input } from "@/ui/input";

import {
  useCreateTopic,
  useDeleteTopic,
  useDismissTopic,
  useKeepTopic,
  useMoveTopic,
  useRenameTopic,
  useTopicTree,
  type TopicMove,
  type TopicNode,
} from "./api";
import { MergeTopicDialog } from "./MergeTopicDialog";
import { ReviewBar } from "./ReviewBar";
import { TopicMapPanel } from "./TopicMapPanel";
import { TopicPagesDialog } from "./TopicPagesDialog";
import { EmptyState } from "./EmptyState";
import { LoadingRows } from "./LoadingRows";
import { aiDescendants, unreviewedOnly } from "./topicReview";
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
  /** The Review filter is on: the tree is cut down, so moves are off. */
  filtering: boolean;
  add: (name: string, parentId: string | null) => Promise<void>;
  rename: (topic: TopicNode, name: string) => Promise<void>;
  move: (topic: TopicNode, target: TopicMove) => Promise<void>;
  askDelete: (topic: TopicNode) => void;
  showPages: (topic: TopicNode) => void;
  // Reviewing an AI topic (decision 0009).
  keep: (topic: TopicNode) => void;
  askMerge: (topic: TopicNode) => void;
  dismiss: (topic: TopicNode) => void;
};

export function TopicTree({ moduleId }: { moduleId: string }) {
  const tree = useTopicTree(moduleId);
  const createTopic = useCreateTopic(moduleId);
  const renameTopic = useRenameTopic(moduleId);
  const moveTopic = useMoveTopic(moduleId);
  const deleteTopic = useDeleteTopic(moduleId);
  const keepTopic = useKeepTopic(moduleId);
  const dismissTopic = useDismissTopic(moduleId);
  const [error, setError] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<TopicNode | null>(null);
  const [toDismiss, setToDismiss] = useState<TopicNode | null>(null);
  const [merging, setMerging] = useState<TopicNode | null>(null);
  const [pagesOf, setPagesOf] = useState<TopicNode | null>(null);
  const [filtering, setFiltering] = useState(false);

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
    busy: moveTopic.isPending || keepTopic.isPending || dismissTopic.isPending,
    filtering,
    add: (name, parentId) => run(() => createTopic.mutateAsync({ name, parentId })),
    rename: (topic, name) => run(() => renameTopic.mutateAsync({ topicId: topic.id, name })),
    move: (topic, target) => run(() => moveTopic.mutateAsync({ topicId: topic.id, ...target })),
    askDelete: setToDelete,
    showPages: setPagesOf,
    keep: (topic) => run(() => keepTopic.mutateAsync(topic.id)).catch(() => {}),
    askMerge: setMerging,
    dismiss: (topic) => {
      // With AI subtopics it takes them along, so ask first.
      if (aiDescendants(topic) > 0) setToDismiss(topic);
      else run(() => dismissTopic.mutateAsync(topic.id)).catch(() => {});
    },
  };

  const subtopics = toDelete ? countDescendants(toDelete) : 0;
  const aiSubtopics = toDismiss ? aiDescendants(toDismiss) : 0;
  const shown = filtering ? unreviewedOnly(tree.data ?? []) : (tree.data ?? []);

  return (
    <section aria-labelledby="topics-heading">
      <h2 id="topics-heading" className="type-h2 mb-2">
        Topics
      </h2>
      <p className="text-muted mb-6 max-w-2xl text-sm">
        Build the module's topic tree. Use the arrows to reorder, indent and outdent. Topics marked
        AI were suggested from your materials: keep, rename, merge or dismiss each one, and it
        becomes yours. Click a topic to see its pages.
      </p>

      <TopicMapPanel moduleId={moduleId} aiTopics={countAi(tree.data ?? [])} />
      <ReviewBar moduleId={moduleId} filtering={filtering} onFilter={setFiltering} />

      {error && (
        <p role="alert" className="text-danger mb-3 text-sm">
          {error}
        </p>
      )}

      {tree.isPending && <LoadingRows label="Loading topics…" rows={4} rowClassName="h-11" />}
      {tree.isError && (
        <p role="alert" className="text-danger text-sm">
          Couldn't load topics: {tree.error.message}
        </p>
      )}
      {tree.data?.length === 0 && (
        <EmptyState icon={ListTree} className="mb-4">
          No topics yet. Add the first one below.
        </EmptyState>
      )}
      {filtering && tree.data && shown.length === 0 && (
        <EmptyState icon={Check} className="mb-4">
          Every AI topic has been reviewed.
        </EmptyState>
      )}
      {shown.length > 0 && (
        <div className="surface-card rounded-xl p-2 sm:p-3">
          <TopicList nodes={shown} parent={null} actions={actions} label="Topics" />
        </div>
      )}

      <AddTopicForm
        label="New topic"
        placeholder="Add a topic"
        onAdd={(name) => actions.add(name, null)}
        className="mt-4"
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
      <ConfirmDialog
        open={toDismiss !== null}
        onOpenChange={(open) => !open && setToDismiss(null)}
        title={`Dismiss “${toDismiss?.name ?? ""}”?`}
        description={`This also dismisses its ${aiSubtopics} AI subtopic${aiSubtopics === 1 ? "" : "s"}; your own subtopics move up. Building the topic map again won't add them back, and you can restore them from Dismissed topics.`}
        confirmLabel="Dismiss"
        onConfirm={() => dismissTopic.mutateAsync(toDismiss!.id)}
      />
      {merging && tree.data && (
        <MergeTopicDialog
          moduleId={moduleId}
          topic={merging}
          tree={tree.data}
          onClose={() => setMerging(null)}
        />
      )}
      {pagesOf && (
        <TopicPagesDialog moduleId={moduleId} topic={pagesOf} onClose={() => setPagesOf(null)} />
      )}
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
      className={parent ? "border-line ml-5 border-l pl-2 sm:ml-6 sm:pl-3" : "divide-line divide-y"}
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

type RowAction = {
  key: string;
  /** The visible menu label; the inline button's name is `${label}: ${topic}`. */
  label: string;
  menuLabel?: string;
  icon: LucideIcon;
  onSelect: () => void;
  disabled?: boolean;
  title?: string;
  destructive?: boolean;
  /** It opens an input that takes focus, so from the menu it waits until the menu has closed. */
  movesFocus?: boolean;
};

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
  // A menu action that opens an input runs once the menu has closed and let go of focus.
  const afterClose = useRef<(() => void) | null>(null);

  const moves = [
    { action: "up", label: "Move up", icon: ArrowUp },
    { action: "down", label: "Move down", icon: ArrowDown },
    { action: "outdent", label: "Outdent", icon: ArrowLeft },
    { action: "indent", label: "Indent", icon: ArrowRight },
  ] as const;

  const moveActions: RowAction[] = moves.map(({ action, label, icon }) => {
    const target = moveTarget(action, siblings, index, parent);
    return {
      key: action,
      label,
      icon,
      disabled: !target || actions.busy || actions.filtering,
      onSelect: () => target && actions.move(node, target).catch(() => {}),
    };
  });
  const editActions: RowAction[] = [
    {
      key: "rename",
      label: "Rename",
      icon: Pencil,
      movesFocus: true,
      onSelect: () => setRenaming(true),
    },
    {
      key: "add",
      label: "Add subtopic to",
      menuLabel: "Add subtopic",
      icon: Plus,
      movesFocus: true,
      onSelect: () => setAdding(true),
    },
  ];
  const reviewActions: RowAction[] =
    node.source === "ai"
      ? [
          {
            key: "keep",
            label: "Keep",
            icon: Check,
            title: "Keep it as it is",
            disabled: actions.busy,
            onSelect: () => actions.keep(node),
          },
          {
            key: "merge",
            label: "Merge into",
            menuLabel: "Merge into…",
            icon: GitMerge,
            title: "Merge into another topic",
            onSelect: () => actions.askMerge(node),
          },
          {
            key: "dismiss",
            label: "Dismiss",
            icon: X,
            title: "Dismiss: remove it and never add it again",
            disabled: actions.busy,
            onSelect: () => actions.dismiss(node),
          },
        ]
      : [
          {
            key: "delete",
            label: "Delete",
            icon: Trash2,
            destructive: true,
            onSelect: () => actions.askDelete(node),
          },
        ];
  const rowActions = [...moveActions, ...editActions, ...reviewActions];

  return (
    <li className="py-0.5">
      <div className="group hover:bg-subtle flex min-h-11 flex-wrap items-center gap-x-2 gap-y-1 rounded-md py-1 pr-1 pl-3 transition-colors">
        {node.source === "ai" && !renaming && (
          <span aria-hidden className="bg-primary size-2 shrink-0 rounded-full" />
        )}
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
            onClick={() => actions.showPages(node)}
            className={cn(
              "min-w-[8rem] flex-1 cursor-pointer truncate rounded-sm py-1.5 text-left text-base",
              // Chapters (top level) carry the weight; subtopics read as body text.
              parent ? "font-normal" : "font-semibold",
            )}
            title="Show its linked pages"
          >
            {node.name}
          </button>
        )}
        {!renaming && (
          <span className="flex shrink-0 items-center gap-2">
            {node.linked_pages > 0 && (
              <span className="text-muted tabular text-sm">
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

        {/* Mouse and keyboard: the icons appear on hover, or once one of them has focus (they
            stay in the tab order). Touch has no hover, so it gets a single "…" menu instead. */}
        <div className="ml-auto flex shrink-0 flex-wrap items-center opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100 pointer-coarse:hidden">
          {rowActions.map(({ key, label, icon: Icon, onSelect, disabled, title }) => (
            <Button
              key={key}
              variant="ghost"
              size="icon-sm"
              aria-label={`${label}: ${node.name}`}
              title={title}
              disabled={disabled}
              onClick={onSelect}
            >
              <Icon aria-hidden />
            </Button>
          ))}
        </div>
        <DropdownMenu>
          <MoreButton
            label={`Actions for ${node.name}`}
            className="ml-auto hidden pointer-coarse:inline-flex"
          />
          <DropdownMenuContent
            onCloseAutoFocus={(event) => {
              const run = afterClose.current;
              afterClose.current = null;
              if (run) {
                event.preventDefault();
                run();
              }
            }}
          >
            {rowActions.map((action, i) => (
              <Fragment key={action.key}>
                {(i === moveActions.length || action.destructive) && <DropdownMenuSeparator />}
                <DropdownMenuItem
                  destructive={action.destructive}
                  disabled={action.disabled}
                  onSelect={() => {
                    if (action.movesFocus) afterClose.current = action.onSelect;
                    else action.onSelect();
                  }}
                >
                  <action.icon aria-hidden />
                  {action.menuLabel ?? action.label}
                </DropdownMenuItem>
              </Fragment>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
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
          className="mt-1 mb-2 ml-5 sm:ml-9"
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
    <form onSubmit={submit} className={cn("flex flex-wrap items-center gap-2", className)}>
      <Input
        aria-label={label}
        placeholder={placeholder}
        value={name}
        autoFocus={autoFocus}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => e.key === "Escape" && onDone?.()}
        maxLength={200}
        className="max-w-sm flex-1 basis-48"
      />
      <Button type="submit" variant="outline" disabled={!name.trim()}>
        Add
      </Button>
      {onDone && (
        <Button type="button" variant="ghost" onClick={onDone}>
          Done
        </Button>
      )}
    </form>
  );
}
