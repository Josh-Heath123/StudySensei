export const taskKeys = {
  all: ["tasks"] as const,
  forModule: (moduleId: string) => ["tasks", "module", moduleId] as const,
};
