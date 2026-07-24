/**
 * Global test setup for Vitest.
 *
 * Registers jest-dom matchers (for example, `toBeInTheDocument`) and clears any per-test module and
 * DOM state between test cases so component tests stay isolated.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});
