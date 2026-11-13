import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

import type { MaterialKind } from "./kinds";

export type Material = components["schemas"]["MaterialOut"];
export type MaterialChanges = components["schemas"]["MaterialUpdate"];

export type NewMaterial = { file: File; kind: MaterialKind; title: string; allowAi: boolean };

/** How often the list refreshes while something is still being processed. */
export const POLL_MS = 2000;

export const materialKeys = {
  list: (moduleId: string) => ["materials", moduleId] as const,
};

const inFlight = (m: Material) => m.status === "uploaded" || m.status === "processing";

/** The module's materials, refreshed every 2 s while any is waiting or processing. */
export function useMaterials(moduleId: string) {
  return useQuery({
    queryKey: materialKeys.list(moduleId),
    queryFn: () =>
      unwrap(
        api.GET("/modules/{module_id}/materials", { params: { path: { module_id: moduleId } } }),
      ),
    refetchInterval: (query) => (query.state.data?.some(inFlight) ? POLL_MS : false),
  });
}

export function useUploadMaterial(moduleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, kind, title, allowAi }: NewMaterial) =>
      unwrap(
        api.POST("/modules/{module_id}/materials", {
          params: { path: { module_id: moduleId } },
          // OpenAPI types a binary field as a string; the File goes into the form below.
          body: { file: file.name, kind, title: title.trim() || null, allow_ai: allowAi },
          bodySerializer: (body) => {
            const form = new FormData();
            form.append("file", file, file.name);
            form.append("kind", body.kind);
            if (body.title) form.append("title", body.title);
            form.append("allow_ai", String(body.allow_ai));
            return form;
          },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: materialKeys.list(moduleId) }),
  });
}

function useMaterialMutation<TArgs>(
  moduleId: string,
  mutationFn: (args: TArgs) => Promise<unknown>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSettled: () => queryClient.invalidateQueries({ queryKey: materialKeys.list(moduleId) }),
  });
}

export function useUpdateMaterial(moduleId: string) {
  return useMaterialMutation(
    moduleId,
    ({ id, changes }: { id: string; changes: MaterialChanges }) =>
      unwrap(
        api.PATCH("/materials/{material_id}", {
          params: { path: { material_id: id } },
          body: changes,
        }),
      ),
  );
}

export function useDeleteMaterial(moduleId: string) {
  return useMaterialMutation(moduleId, (id: string) =>
    unwrap(api.DELETE("/materials/{material_id}", { params: { path: { material_id: id } } })),
  );
}

export function useRetryMaterial(moduleId: string) {
  return useMaterialMutation(moduleId, (id: string) =>
    unwrap(api.POST("/materials/{material_id}/retry", { params: { path: { material_id: id } } })),
  );
}

export type PageSummary = components["schemas"]["PageSummary"];
export type Page = components["schemas"]["PageOut"];

/** A material's extracted pages, without their text. */
export function usePages(materialId: string) {
  return useQuery({
    queryKey: ["materials", "pages", materialId],
    queryFn: () =>
      unwrap(
        api.GET("/materials/{material_id}/pages", {
          params: { path: { material_id: materialId } },
        }),
      ),
  });
}

/** One page's extracted text. */
export function usePage(materialId: string, pageNumber: number | null) {
  return useQuery({
    queryKey: ["materials", "pages", materialId, pageNumber],
    enabled: pageNumber !== null,
    queryFn: () =>
      unwrap(
        api.GET("/materials/{material_id}/pages/{page_number}", {
          params: { path: { material_id: materialId, page_number: pageNumber ?? 1 } },
        }),
      ),
  });
}
