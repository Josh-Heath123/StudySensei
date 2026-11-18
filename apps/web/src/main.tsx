import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// Self-hosted font (no Google Fonts calls): Inter variable for everything.
import "@fontsource-variable/inter";

import { App } from "./app/App";
import { followSystemTheme } from "./lib/appearance";
import "./index.css";

// index.html set the theme before the first paint; this keeps "System" following the OS.
followSystemTheme();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
