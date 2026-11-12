import { useState, type FormEvent } from "react";

import { ApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";
import { Button } from "@/ui/button";
import { Input } from "@/ui/input";
import { Label } from "@/ui/label";

import type { Module, ModuleInput } from "./api";
import { COLOUR_PRESETS } from "./colours";

type Props = {
  initial?: Module;
  submitLabel: string;
  onSubmit: (values: ModuleInput) => Promise<unknown>;
  onCancel: () => void;
};

export function ModuleForm({ initial, submitLabel, onSubmit, onCancel }: Props) {
  const [code, setCode] = useState(initial?.code ?? "");
  const [name, setName] = useState(initial?.name ?? "");
  const [semester, setSemester] = useState(initial?.semester ?? "");
  const [colour, setColour] = useState(initial?.colour ?? COLOUR_PRESETS[0]!);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await onSubmit({
        code: code.trim(),
        name: name.trim(),
        colour,
        semester: semester.trim() || null,
      });
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setSaving(false);
    }
  }

  // A 409 is always about the code, so show it right under that field.
  const codeError = error instanceof ApiError && error.status === 409 ? error.message : null;
  const formError = error && !codeError ? error.message : null;

  return (
    <form onSubmit={handleSubmit} className="grid gap-4" noValidate>
      <div className="grid grid-cols-[8rem_1fr] gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor="module-code">Code</Label>
          <Input
            id="module-code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="COS330"
            maxLength={20}
            required
            aria-invalid={codeError ? true : undefined}
            aria-describedby={codeError ? "module-code-error" : undefined}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="module-name">Name</Label>
          <Input
            id="module-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Software Architecture"
            maxLength={200}
            required
          />
        </div>
        {codeError && (
          <p id="module-code-error" role="alert" className="text-destructive col-span-2 text-sm">
            {codeError}
          </p>
        )}
      </div>

      <div className="grid gap-1.5">
        <Label htmlFor="module-semester">
          Semester <span className="text-muted-foreground font-normal">(optional)</span>
        </Label>
        <Input
          id="module-semester"
          value={semester}
          onChange={(e) => setSemester(e.target.value)}
          placeholder="2026-S2"
          maxLength={20}
        />
      </div>

      <fieldset className="grid gap-2">
        <legend className="mb-1.5 text-sm font-medium">Colour</legend>
        <div className="flex flex-wrap items-center gap-2">
          {COLOUR_PRESETS.map((preset) => (
            <button
              key={preset}
              type="button"
              aria-label={`Colour ${preset}`}
              aria-pressed={colour.toUpperCase() === preset}
              onClick={() => setColour(preset)}
              className={cn(
                "size-7 rounded-full border-2 border-transparent transition",
                colour.toUpperCase() === preset &&
                  "border-foreground ring-background ring-2 ring-inset",
              )}
              style={{ backgroundColor: preset }}
            />
          ))}
          <label className="text-muted-foreground ml-1 flex items-center gap-2 text-sm">
            Custom
            <input
              type="color"
              value={colour}
              onChange={(e) => setColour(e.target.value.toUpperCase())}
              className="size-7 cursor-pointer rounded border bg-transparent"
            />
          </label>
        </div>
      </fieldset>

      {formError && (
        <p role="alert" className="text-destructive text-sm">
          {formError}
        </p>
      )}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={saving || !code.trim() || !name.trim()}>
          {saving ? "Saving…" : submitLabel}
        </Button>
      </div>
    </form>
  );
}
