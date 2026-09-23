"use client";

import {
  BrainCircuit,
  Check,
  ChevronRight,
  CircleAlert,
  FileAudio,
  FileText,
  Film,
  Library,
  Loader2,
  Sparkles,
  StickyNote,
  Youtube,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { type ReadingLibraryMaterial } from "@/lib/reading-workspace-api";
import { readingFailureMessage } from "@/lib/reading-failure";

export function iconForMaterial(material: ReadingLibraryMaterial) {
  if (material.source_kind === "youtube") return Youtube;
  if (material.source_kind === "bilibili") return Film;
  if (material.render_mode === "video") return Film;
  if (material.render_mode === "audio") return FileAudio;
  return FileText;
}

export function MenuItem({
  icon: Icon,
  label,
  onClick,
  disabled,
  hint,
  active,
  spinning,
}: {
  icon: typeof StickyNote;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  /** A second line under the label — why it is disabled, or what it acts on. */
  hint?: string;
  /** A setting that is on. Toggles report it; plain actions leave it unset. */
  active?: boolean;
  spinning?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      role={active === undefined ? undefined : "menuitemcheckbox"}
      aria-checked={active}
      className="flex w-full items-start gap-2 rounded-md px-2.5 py-2 text-left text-[var(--foreground)] transition hover:bg-[var(--muted)] disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:bg-transparent"
    >
      <Icon
        size={13}
        className={`mt-[2px] shrink-0 ${
          active ? "text-[var(--primary)]" : "text-[var(--muted-foreground)]"
        } ${spinning ? "animate-spin" : ""}`}
      />
      <span className="min-w-0 flex-1">
        <span className="block">{label}</span>
        {hint ? (
          <span className="mt-0.5 block text-[10.5px] leading-snug text-[var(--muted-foreground)]">
            {hint}
          </span>
        ) : null}
      </span>
      {active ? (
        <Check size={13} className="mt-[2px] shrink-0 text-[var(--primary)]" />
      ) : null}
    </button>
  );
}

export function CompanionWelcome({
  title,
  onAction,
  suggestions = [],
  tools = [],
}: {
  title: string;
  onAction: (prompt: string) => void;
  /** Page-level reading actions (a quiz on this page, say), one click each. */
  tools?: { key: string; label: string; onClick: () => void }[];
  /**
   * Openers written against this material. Empty falls back to the three
   * generic lines below, which are true of any document — fine as a floor,
   * wrong as the default.
   */
  suggestions?: string[];
}) {
  const { t } = useTranslation();
  return (
    <div className="mx-auto flex min-h-full max-w-[300px] flex-col items-center justify-center py-10 text-center">
      <span className="flex size-12 items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--muted)] text-[var(--primary)]">
        <BrainCircuit size={20} />
      </span>
      <p className="mt-4 font-serif text-[17px] font-medium tracking-[-0.01em]">
        {t("Read with a grounded companion")}
      </p>
      <p className="mt-2 text-[12px] leading-relaxed text-[var(--muted-foreground)]">
        {title
          ? t(
              "Ask anything about {{title}}, or select a passage in the document to explain, translate or discuss it.",
              { title },
            )
          : t("Add material to begin a reading conversation.")}
      </p>
      <div className="mt-5 w-full space-y-2 text-left">
        {(suggestions.length
          ? suggestions
          : [
              t("Explain the key argument"),
              t("Challenge this evidence"),
              t("Turn this into study notes"),
            ]
        ).map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => onAction(item)}
            className="flex w-full items-start gap-2 rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-left text-[12px] leading-relaxed text-[var(--muted-foreground)] transition hover:border-[color-mix(in_srgb,var(--primary)_40%,transparent)] hover:text-[var(--foreground)] dark:border-[var(--border)] dark:bg-[var(--card)]"
          >
            <ChevronRight
              size={12}
              className="mt-[3px] shrink-0 text-[var(--primary)]"
            />
            <span className="min-w-0 flex-1">{item}</span>
          </button>
        ))}
      </div>
      {tools.length ? (
        <div className="mt-4 flex flex-wrap justify-center gap-1.5">
          {tools.map((tool) => (
            <button
              key={tool.key}
              type="button"
              onClick={tool.onClick}
              className="inline-flex h-7 items-center gap-1.5 rounded-full border border-[var(--border)] px-2.5 text-[11.5px] font-medium text-[var(--muted-foreground)] transition hover:border-[color-mix(in_srgb,var(--primary)_40%,transparent)] hover:text-[var(--foreground)]"
            >
              <Sparkles size={11} className="text-[var(--primary)]" />
              {tool.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function EmptyWorkspace({ onAdd }: { onAdd: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex h-full flex-col items-center justify-center text-center">
      <Library size={25} className="text-[var(--primary)]" />
      <p className="mt-3 font-serif text-[18px] font-medium">
        {t("Add material to begin")}
      </p>
      <button
        type="button"
        onClick={onAdd}
        className="mt-5 rounded-xl bg-[var(--primary)] px-4 py-2 text-[11px] font-semibold text-[var(--primary-foreground)]"
      >
        {t("Add material")}
      </button>
    </div>
  );
}

export function MaterialProcessing({
  material,
}: {
  material: ReadingLibraryMaterial;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex h-full flex-col items-center justify-center text-center">
      <Loader2 size={24} className="animate-spin text-[var(--primary)]" />
      <p className="mt-4 font-serif text-[18px] font-medium">
        {t("Preparing {{title}}", { title: material.title })}
      </p>
      <p className="mt-2 text-[10.5px] text-[var(--muted-foreground)]">
        {t("Extracting structure and grounded passages…")} {material.progress}%
      </p>
    </div>
  );
}

export function MaterialFailure({
  material,
  onRetry,
}: {
  material: ReadingLibraryMaterial;
  onRetry: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState("");

  const retry = async () => {
    setRetrying(true);
    setRetryError("");
    try {
      await onRetry();
    } catch (caught) {
      setRetryError(
        caught instanceof Error
          ? caught.message
          : t("Try importing this material again."),
      );
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div className="flex h-full flex-col items-center justify-center px-8 text-center">
      <CircleAlert size={24} className="text-red-600" />
      <p className="mt-4 font-serif text-[18px] font-medium">
        {t("This material could not be prepared")}
      </p>
      <p className="mt-2 max-w-lg text-[10.5px] leading-relaxed text-[var(--muted-foreground)]">
        {readingFailureMessage(material, t) ||
          t("Try importing this material again.")}
      </p>
      {retryError && (
        <p className="mt-2 max-w-lg text-[10.5px] text-red-700">{retryError}</p>
      )}
      <button
        type="button"
        onClick={() => void retry()}
        disabled={retrying}
        className="mt-5 inline-flex h-9 items-center gap-2 rounded-xl bg-[var(--primary)] px-4 text-[11px] font-semibold text-[var(--primary-foreground)] transition hover:opacity-90 disabled:cursor-wait disabled:opacity-60"
      >
        {retrying && <Loader2 size={12} className="animate-spin" />}
        {retrying ? t("Retrying…") : t("Retry")}
      </button>
    </div>
  );
}
