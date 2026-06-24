import { createBrowserRouter } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { ProjectPage } from "./pages/ProjectPage";
import { TicketDetailPage } from "./pages/TicketDetailPage";
import { ProjectListPage } from "./pages/ProjectListPage";

export const router = createBrowserRouter([
  {
    element: <AppShell><ProjectListPage /></AppShell>,
    path: "/projects",
  },
  {
    element: <AppShell><ProjectPage /></AppShell>,
    path: "/projects/:projectId",
  },
  {
    element: <AppShell><TicketDetailPage /></AppShell>,
    path: "/tickets/:ticketId",
  },
  {
    element: <AppShell><ProjectListPage /></AppShell>,
    path: "/",
  },
]);
