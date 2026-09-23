import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { initI18n } from "@/i18n/init";

initI18n("en");

const fixture = vi.hoisted(() => {
  const rendition = {
    display: vi.fn(async () => undefined),
    currentLocation: vi.fn(() => ({ start: { cfi: "epubcfi(/6/2)" } })),
    next: vi.fn(async () => undefined),
    prev: vi.fn(async () => undefined),
    resize: vi.fn(),
    spread: vi.fn(),
    destroy: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
    annotations: { highlight: vi.fn(), remove: vi.fn() },
    hooks: { content: { register: vi.fn() } },
    themes: {
      register: vi.fn(),
      select: vi.fn(),
      fontSize: vi.fn(),
      override: vi.fn(),
      removeOverride: vi.fn(),
    },
  };
  return {
    rendition,
    renderTo: vi.fn(() => rendition),
    apiFetch: vi.fn(async () => ({
      ok: true,
      arrayBuffer: async () => new ArrayBuffer(8),
    })),
  };
});

vi.mock("epubjs", () => ({
  default: () => ({
    open: async () => undefined,
    ready: Promise.resolve(),
    renderTo: fixture.renderTo,
    spine: { get: () => ({ href: "one.xhtml" }) },
    destroy: vi.fn(),
  }),
}));
vi.mock("@/lib/api", () => ({ apiFetch: fixture.apiFetch }));
vi.mock("@/lib/reading-api", () => ({
  rawMaterialUrl: () => "/api/reading/materials/book/raw",
  getReadingPosition: async () => ({ locator: 1 }),
  saveReadingPosition: vi.fn(async () => undefined),
}));

import { EpubDocumentView } from "@/components/reading/EpubDocumentView";

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    x: 0,
    y: 0,
    top: 0,
    left: 0,
    right: 900,
    bottom: 600,
    width: 900,
    height: 600,
    toJSON: () => ({}),
  });
});

it("opens EPUB in single-page mode and keeps the CFI when switching spreads", async () => {
  render(
    <EpubDocumentView
      materialId="book"
      unitCount={1}
      unitRefs={[]}
      annotations={[]}
      jump={null}
      onSelection={() => undefined}
    />,
  );

  await waitFor(() =>
    expect(fixture.renderTo).toHaveBeenCalledWith(
      expect.any(Element),
      expect.objectContaining({ spread: "none" }),
    ),
  );
  fireEvent.click(screen.getByRole("button", { name: "Switch to two-page spread" }));

  await waitFor(() => expect(fixture.rendition.spread).toHaveBeenCalledWith("auto"));
  await waitFor(() =>
    expect(fixture.rendition.resize).toHaveBeenCalledWith(900, 600),
  );
  expect(fixture.rendition.display).toHaveBeenCalledWith("epubcfi(/6/2)");
  expect(JSON.parse(localStorage.getItem("dt.reader.textPreferences") || "{}"))
    .toMatchObject({ spreadMode: "auto" });
});

it("applies saved typography and theme to EPUB content", async () => {
  localStorage.setItem(
    "dt.reader.textPreferences",
    JSON.stringify({ fontSize: 23, serif: false, readerTheme: "night", spreadMode: "auto" }),
  );
  render(
    <EpubDocumentView
      materialId="book"
      unitCount={1}
      unitRefs={[]}
      annotations={[]}
      jump={null}
      onSelection={() => undefined}
    />,
  );

  await waitFor(() =>
    expect(fixture.renderTo).toHaveBeenCalledWith(
      expect.any(Element),
      expect.objectContaining({ spread: "auto" }),
    ),
  );
  expect(fixture.rendition.themes.fontSize).toHaveBeenCalledWith("23px");
  expect(fixture.rendition.themes.override).toHaveBeenCalledWith(
    "background-color",
    "#16181d",
    true,
  );
  fireEvent.click(screen.getByRole("button", { name: "Reset reading display" }));
  await waitFor(() =>
    expect(fixture.rendition.themes.removeOverride).toHaveBeenCalledWith(
      "background-color",
    ),
  );
  expect(JSON.parse(localStorage.getItem("dt.reader.textPreferences") || "{}"))
    .toMatchObject({ fontSize: 17, readerTheme: "auto", spreadMode: "none" });
});
