/**
 * SC-005 gate: Zero inline style props in .tsx files after migration.
 * Permitted exception: lines with "swatch-color-required" comment in ThemeSwitcher.
 *
 * This test runs `grep` on the src/ directory and fails if any non-exempt
 * style= attribute is found.
 *
 * NOTE: This test will FAIL before the design system migration is complete.
 * It is the final quality gate for Phase 7 (T045).
 */
import { describe, it, expect } from "vitest";
import { execSync } from "child_process";
import { resolve } from "path";

const SRC_DIR = resolve(__dirname, "../../src");

describe("SC-005: No inline style props in .tsx source files", () => {
  it("grep finds zero style= usages (excluding swatch-color-required exemption)", () => {
    let output = "";
    try {
      output = execSync(
        `grep -rn "style=" "${SRC_DIR}" --include="*.tsx" | grep -v "swatch-color-required"`,
        { encoding: "utf8" }
      );
    } catch (err: unknown) {
      // grep exits 1 when no matches — that's the success case
      const error = err as { status?: number; stdout?: string };
      if (error.status === 1) {
        output = "";
      } else {
        throw err;
      }
    }

    if (output.trim().length > 0) {
      const lines = output.trim().split("\n");
      const relative = lines.map((l) => l.replace(SRC_DIR, "src"));
      throw new Error(
        `SC-005 FAIL: Found ${lines.length} inline style prop(s) — all must be removed (FR-014):\n` +
          relative.join("\n")
      );
    }

    expect(output.trim()).toBe("");
  });
});
