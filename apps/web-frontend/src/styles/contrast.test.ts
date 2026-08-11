/**
 * WCAG-AA contrast regression test for the design tokens.
 *
 * The axe check runs in jsdom, which cannot compute resolved colors, so it cannot catch a
 * low-contrast token pair (this gap produced CR-WEB-MEDIUM-008: dark-theme button backgrounds below
 * 4.5:1 for white text). This test closes that gap deterministically: it parses `tokens.css`,
 * extracts the light (`:root`) and dark (`:root[data-theme="dark"]`) palettes, and asserts that every
 * foreground/background pair used for normal-size text meets the WCAG-AA 4.5:1 ratio in both themes.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Read the token stylesheet source once for parsing.
 *
 * Resolved from the Vitest working directory (`apps/web-frontend`) rather than `import.meta.url`,
 * because under the jsdom test environment `import.meta.url` is not a `file:` URL.
 */
const TOKENS_CSS = readFileSync(resolve(process.cwd(), "src/styles/tokens.css"), "utf8");

/**
 * Extract the custom-property map declared directly inside a selector block.
 *
 * Args:
 *   selectorPattern: A regex matching the selector and its opening brace (the block has no nested
 *     braces, so it ends at the next closing brace).
 *
 * Returns:
 *   A map from custom-property name (without the leading `--`) to its trimmed value.
 */
function parseBlock(selectorPattern: RegExp): Map<string, string> {
  const match = selectorPattern.exec(TOKENS_CSS);
  if (!match) {
    throw new Error(`Selector not found in tokens.css: ${selectorPattern}`);
  }
  const start = match.index + match[0].length;
  const end = TOKENS_CSS.indexOf("}", start);
  const body = TOKENS_CSS.slice(start, end);
  const vars = new Map<string, string>();
  for (const decl of body.matchAll(/--([\w-]+):\s*([^;]+);/g)) {
    vars.set(decl[1]!, decl[2]!.trim());
  }
  return vars;
}

/**
 * Convert one sRGB channel (0–255) to its linear-light value.
 *
 * Args:
 *   channel: The 8-bit channel value.
 *
 * Returns:
 *   The linearized channel in [0, 1] per the WCAG relative-luminance definition.
 */
function linearize(channel: number): number {
  const c = channel / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/**
 * Compute the WCAG relative luminance of a `#rrggbb` color.
 *
 * Args:
 *   hex: A six-digit hex color string (with leading `#`).
 *
 * Returns:
 *   The relative luminance in [0, 1].
 */
function luminance(hex: string): number {
  const value = hex.replace("#", "");
  const r = Number.parseInt(value.slice(0, 2), 16);
  const g = Number.parseInt(value.slice(2, 4), 16);
  const b = Number.parseInt(value.slice(4, 6), 16);
  return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b);
}

/**
 * Compute the WCAG contrast ratio between two colors.
 *
 * Args:
 *   fg: The foreground (text) color.
 *   bg: The background color.
 *
 * Returns:
 *   The contrast ratio (1–21).
 */
function contrast(fg: string, bg: string): number {
  const l1 = luminance(fg);
  const l2 = luminance(bg);
  const [light, dark] = l1 >= l2 ? [l1, l2] : [l2, l1];
  return (light + 0.05) / (dark + 0.05);
}

/** WCAG-AA minimum contrast ratio for normal-size text. */
const AA_NORMAL = 4.5;

/** The foreground/background token pairs that render normal-size text. */
const TEXT_PAIRS: ReadonlyArray<{ label: string; fg: string; bg: string }> = [
  { label: "body text on background", fg: "color-text", bg: "color-bg" },
  { label: "muted text on background", fg: "color-text-muted", bg: "color-bg" },
  { label: "primary button text on primary", fg: "color-primary-text", bg: "color-primary" },
  {
    label: "primary button text on primary hover",
    fg: "color-primary-text",
    bg: "color-primary-hover",
  },
  { label: "danger button text on danger", fg: "color-danger-text", bg: "color-danger" },
  {
    label: "danger button text on danger hover",
    fg: "color-danger-text",
    bg: "color-danger-hover",
  },
];

/** The token palettes to verify, keyed by theme. */
const THEMES: ReadonlyArray<{ name: string; selector: RegExp }> = [
  { name: "light", selector: /:root\s*\{/ },
  { name: "dark", selector: /:root\[data-theme="dark"\]\s*\{/ },
];

describe("design token contrast (WCAG-AA)", () => {
  for (const theme of THEMES) {
    describe(`${theme.name} theme`, () => {
      const palette = parseBlock(theme.selector);
      for (const pair of TEXT_PAIRS) {
        it(`${pair.label} meets 4.5:1`, () => {
          const fg = palette.get(pair.fg);
          const bg = palette.get(pair.bg);
          expect(fg, `missing --${pair.fg}`).toBeDefined();
          expect(bg, `missing --${pair.bg}`).toBeDefined();
          const ratio = contrast(fg!, bg!);
          expect(
            ratio,
            `${pair.label} (${theme.name}): ${fg} on ${bg} = ${ratio.toFixed(2)}:1`,
          ).toBeGreaterThanOrEqual(AA_NORMAL);
        });
      }
    });
  }
});
