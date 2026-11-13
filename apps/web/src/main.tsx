import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// Self-hosted fonts (no Google Fonts calls): Inter for text, Space Grotesk for headings and numerals.
import "@fontsource-variable/inter";
import "@fontsource/space-grotesk/500.css";
import "@fontsource/space-grotesk/700.css";

import { App } from "./app/App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
