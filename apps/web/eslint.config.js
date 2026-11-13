import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "src/lib/api/schema.d.ts", "test-results", "playwright-report"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // The shadcn CLI keeps importing cn from an unrelated npm package called "cn".
      "no-restricted-imports": [
        "error",
        { paths: [{ name: "cn", message: 'Use `import { cn } from "@/lib/utils"`.' }] },
      ],
    },
  },
  {
    // shadcn/ui components export variants next to components by design
    files: ["src/ui/**/*.tsx"],
    rules: { "react-refresh/only-export-components": "off" },
  },
);
