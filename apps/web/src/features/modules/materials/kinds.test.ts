import { checkFile, formatSize, guessKind, MAX_UPLOAD_BYTES, titleFrom } from "./kinds";

describe("guessKind", () => {
  it.each([
    ["L03 Layered architecture.pptx", "slides"],
    ["COS330 Exam 2024.pdf", "past_paper"],
    ["Past paper June 2023.pdf", "past_paper"],
    ["Semester test 1 memo.pdf", "test"],
    ["Assignment 2 brief.pdf", "assignment"],
    ["Tutorial 4.docx", "tutorial"],
    ["Study guide 2026.pdf", "study_guide"],
    ["Module outline.pdf", "outline"],
    ["Lecture notes week 3.pdf", "notes"],
    ["notes.md", "notes"],
    ["whiteboard.jpg", "other"],
    ["random.pdf", "other"],
  ])("%s → %s", (filename, kind) => {
    expect(guessKind(filename)).toBe(kind);
  });

  it("doesn't mistake words that merely contain a keyword", () => {
    expect(guessKind("Latest updates.pdf")).toBe("other"); // "test" inside "Latest"
    expect(guessKind("Contest results.pdf")).toBe("other");
  });
});

describe("titleFrom", () => {
  it("drops the extension and tidies separators", () => {
    expect(titleFrom("Week_3-layers.pdf")).toBe("Week 3-layers");
    expect(titleFrom("  notes .md")).toBe("notes");
    expect(titleFrom(".pdf")).toBe("Untitled");
  });

  it("keeps titles to 200 characters", () => {
    expect(titleFrom(`${"a".repeat(250)}.pdf`)).toHaveLength(200);
  });
});

describe("checkFile", () => {
  const file = (name: string, size = 10) => ({ name, size });

  it("accepts the allowed types, in any case", () => {
    for (const name of ["a.pdf", "a.PPTX", "a.docx", "a.md", "a.txt", "a.png", "a.jpg", "a.jpeg"]) {
      expect(checkFile(file(name))).toBeNull();
    }
  });

  it("explains what's wrong otherwise", () => {
    expect(checkFile(file("setup.exe"))).toBe(
      "setup.exe: .exe files can't be uploaded. Use PDF, PPTX, DOCX, MD, TXT, PNG or JPG.",
    );
    expect(checkFile(file("README"))).toMatch(/README: files without an extension/);
    expect(checkFile(file("big.pdf", MAX_UPLOAD_BYTES + 1))).toBe(
      "big.pdf is 50.0 MB; files can be at most 50 MB.",
    );
    expect(checkFile(file("empty.pdf", 0))).toBe("empty.pdf is empty.");
  });
});

describe("formatSize", () => {
  it("uses KB below a megabyte and MB above", () => {
    expect(formatSize(900)).toBe("1 KB");
    expect(formatSize(150 * 1024)).toBe("150 KB");
    expect(formatSize(2.5 * 1024 * 1024)).toBe("2.5 MB");
  });
});
