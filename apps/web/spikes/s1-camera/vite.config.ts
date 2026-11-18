import { defineConfig } from "vite";

// Spike S1's own entry: `npm run spike:s1` serves it on :5175. It isn't in the app's bundle or
// routes (the app builds from apps/web/index.html). localhost counts as secure for the camera.
export default defineConfig({
  root: import.meta.dirname,
  server: { port: 5175, strictPort: true },
  preview: { port: 5175, strictPort: true },
});
