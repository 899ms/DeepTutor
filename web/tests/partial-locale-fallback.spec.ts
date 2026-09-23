import { expect, it } from "vitest";

import { ensureLanguage, initI18n } from "@/i18n/init";

it.each(["fr", "uk"] as const)("uses English copy for a missing %s translation", async (language) => {
  const i18n = initI18n(language);
  await ensureLanguage(language);
  await i18n.changeLanguage(language);

  expect(i18n.t("common.save")).toBe("Save");
});
