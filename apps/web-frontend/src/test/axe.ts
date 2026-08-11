/**
 * Accessibility test helper built on axe-core.
 *
 * Runs the axe accessibility engine over a rendered subtree and fails the test with a readable
 * summary when any violation is found (TASK_01E-5 DoD: "an accessibility check passes on the core
 * screens"). The `color-contrast` rule is disabled here because jsdom does not compute layout or
 * resolved colors, so axe cannot evaluate contrast in this environment; contrast is instead
 * guaranteed by the design tokens (WCAG-AA pairs, see `styles/tokens.css`) and verified visually.
 * All structural rules (labels, roles, names, ARIA, landmarks) run normally.
 */
import axe from "axe-core";

/**
 * Assert that a rendered subtree has no axe accessibility violations.
 *
 * Args:
 *   container: The DOM node to analyze (must be attached to the document).
 *
 * Raises:
 *   Error: When axe reports one or more violations, with a summary of each rule and node count.
 */
export async function expectNoAxeViolations(container: HTMLElement): Promise<void> {
  const results = await axe.run(container, {
    // Evaluate the WCAG 2.0/2.1 level A and AA success criteria (the DoD target). Best-practice
    // rules (e.g. landmark "region") are excluded so pages rendered without the app shell in a unit
    // test are not flagged for a missing <main> that AppLayout provides at runtime.
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] },
    rules: {
      // jsdom cannot compute resolved colors/layout; contrast is enforced via design tokens.
      "color-contrast": { enabled: false },
    },
  });
  if (results.violations.length > 0) {
    const summary = results.violations
      .map((violation) => {
        const targets = violation.nodes.map((node) => node.target.join(" ")).join(", ");
        return `- ${violation.id} (${violation.impact ?? "n/a"}): ${violation.help} [${targets}]`;
      })
      .join("\n");
    throw new Error(`Accessibility violations found:\n${summary}`);
  }
}
