/**
 * Application routes.
 *
 * Public `/login`; the appeal list at `/tickets` behind the authentication guard and the product
 * shell. The index and any unknown path redirect to `/tickets`, which in turn redirects to
 * `/login` when the user is not signed in.
 */
import { Navigate, Route, Routes } from "react-router-dom";
import { LoginPage } from "./features/login/LoginPage";
import { TicketListPage } from "./features/tickets/TicketListPage";
import { RequireAuth } from "./routing/RequireAuth";
import { AppLayout } from "./components/AppLayout";

/**
 * Render the routed application.
 *
 * Returns:
 *   The route tree element.
 */
export function App(): React.JSX.Element {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/tickets"
        element={
          <RequireAuth>
            <AppLayout>
              <TicketListPage />
            </AppLayout>
          </RequireAuth>
        }
      />
      <Route path="/" element={<Navigate to="/tickets" replace />} />
      <Route path="*" element={<Navigate to="/tickets" replace />} />
    </Routes>
  );
}
