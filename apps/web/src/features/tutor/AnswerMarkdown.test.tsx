import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { TooltipProvider } from "@/ui/tooltip";

import AnswerMarkdown from "./AnswerMarkdown";
import { SourcesContext } from "./sourcesContext";
import type { SourceView } from "./turns";

const SOURCES: SourceView[] = [
  { label: "S1", materialId: "m1", title: "CH09", page: 14, pageTitle: null, cited: true },
  { label: "S2", materialId: "m1", title: "CH09", page: 13, pageTitle: "Firewalls", cited: true },
];

function show(text: string, open = vi.fn()) {
  const view = render(
    <TooltipProvider>
      <SourcesContext.Provider value={{ sources: SOURCES, open }}>
        <div data-testid="answer">
          <AnswerMarkdown text={text} />
        </div>
      </SourcesContext.Provider>
    </TooltipProvider>,
  );
  return { ...view, answer: screen.getByTestId("answer"), open };
}

describe("AnswerMarkdown never renders HTML", () => {
  test.each([
    '<img src="x" onerror="alert(1)">',
    "<script>alert(1)</script>",
    '<a href="javascript:alert(1)">click</a>',
    '<iframe src="https://example.com"></iframe>',
    "<b onmouseover=alert(1)>bold</b>",
  ])("%s", (html) => {
    const { answer } = show(`Before ${html} after\n\n${html}`);

    expect(answer.querySelector("img, script, iframe, b, [onerror], [onmouseover]")).toBeNull();
    expect(answer.querySelector('a[href^="javascript"]')).toBeNull();
    expect(answer).toHaveTextContent("Before");
  });

  test("a Markdown link with a dangerous protocol loses its URL", () => {
    const { answer } = show("[click](javascript:alert(1)) and [data](data:text/html,<b>x</b>)");

    for (const link of answer.querySelectorAll("a")) {
      expect(link.getAttribute("href") ?? "").not.toMatch(/^(javascript|data):/i);
    }
  });

  test("safe links open in a new tab without the opener", () => {
    const { answer } = show("[KaTeX](https://katex.org)");

    const link = answer.querySelector("a")!;
    expect(link).toHaveAttribute("href", "https://katex.org");
    expect(link).toHaveAttribute("rel", "noreferrer noopener");
  });
});

describe("AnswerMarkdown's maths", () => {
  test("renders inline and display maths with KaTeX", () => {
    const { answer } = show(
      "Euler: $e^{i\\pi} + 1 = 0$\n\n$$\n\\sum_{k=1}^{n} k = \\frac{n(n+1)}{2}\n$$",
    );

    expect(answer.querySelectorAll(".katex").length).toBeGreaterThanOrEqual(2);
    expect(answer.querySelector(".katex-display")).not.toBeNull();
  });

  test.each([
    "$\\href{javascript:alert(1)}{click}$",
    "$\\url{javascript:alert(1)}$",
    "$\\htmlId{evil}{x}$",
    "$\\htmlStyle{background:url(javascript:alert(1))}{x}$",
    "$\\htmlData{foo=bar}{x}$",
    "$\\includegraphics{https://example.com/x.png}$",
  ])("untrusted KaTeX commands make no link, id, style or image: %s", (tex) => {
    const { answer } = show(tex);

    expect(answer.querySelector("a, img, #evil, [data-foo]")).toBeNull();
    // The TeX source is kept as text (MathML's <annotation>), never as an attribute.
    for (const element of answer.querySelectorAll("*")) {
      for (const attribute of element.attributes) {
        expect(attribute.value).not.toMatch(/javascript:|https:\/\/example/i);
      }
    }
  });

  test("broken maths shows as text instead of throwing", () => {
    const { answer } = show("Oops $\\frac{1}{$ there");

    expect(answer).toHaveTextContent("Oops");
  });
});

describe("AnswerMarkdown's citations", () => {
  test("both bracket forms become chips; clicking one opens its source", async () => {
    const user = userEvent.setup();
    const { open } = show("It tracks state [S1] and【S2】.");

    const chip = screen.getByRole("button", { name: "Source S2: CH09 · page 13: Firewalls" });
    await user.click(chip);
    expect(open).toHaveBeenCalledWith(SOURCES[1]);
    expect(screen.getByRole("button", { name: /^Source S1: CH09 · page 14$/ })).toBeVisible();
  });

  test("hovering or focusing a chip names the material and page", async () => {
    const user = userEvent.setup();
    show("Tracked [S1].");

    await user.tab();
    expect(await screen.findByRole("tooltip")).toHaveTextContent("CH09 · page 14");
  });

  test("a label that wasn't given stays plain text; one in a group still becomes a chip", () => {
    const { answer } = show("Odd [S9]. Mixed [S1, S9].");

    expect(answer).toHaveTextContent("Odd [S9]. Mixed S1[S9].");
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  test("citations inside code stay code", () => {
    const { answer } = show("Use `[S1]` literally:\n\n```\nlabels = [S1]\n```");

    expect(screen.queryByRole("button")).toBeNull();
    expect(answer.querySelectorAll("code")).toHaveLength(2);
  });
});
