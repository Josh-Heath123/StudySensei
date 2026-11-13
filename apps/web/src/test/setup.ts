import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// findBy*/waitFor give up after 1 s by default. The first test in a file also pays for
// loading the app's modules, which on a busy machine running every file in parallel
// (the Stop hook, CI) can take longer than that, so those tests failed now and then.
configure({ asyncUtilTimeout: 3000 });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear(); // the session engine's queue and heartbeat live here
});
