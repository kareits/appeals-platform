/**
 * Application entry point.
 *
 * Wires the global providers — TanStack Query, the authentication context, and the router — and
 * mounts the app. Importing the i18n module initializes react-i18next before first render.
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { initTheme } from "./theme/theme";
import "./i18n";
import "./styles.css";

// Apply the stored theme (light/dark/system) before the first render so a forced choice is honored
// immediately rather than flashing the system default.
initTheme();

/** Shared query client; failed queries are not retried so auth/permission errors surface at once. */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, refetchOnWindowFocus: false },
  },
});

const container = document.getElementById("root");
if (!container) {
  throw new Error("Root container #root not found");
}

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
