import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./AppShell";
import { DashboardPage } from "../pages/DashboardPage";
import { WorkflowCatalogPage } from "../pages/WorkflowCatalogPage";
import { AccessRequestPage } from "../pages/AccessRequestPage";
import { ProcurementRequestPage } from "../pages/ProcurementRequestPage";
import { MaintenanceRequestPage } from "../pages/MaintenanceRequestPage";
import { SessionRunsPage } from "../pages/SessionRunsPage";
import { RunDetailPage } from "../pages/RunDetailPage";
import { RunApprovalsPage } from "../pages/RunApprovalsPage";
import { RunToolCallsPage } from "../pages/RunToolCallsPage";
import { RunAuditTrailPage } from "../pages/RunAuditTrailPage";
import { SessionApprovalsPage } from "../pages/SessionApprovalsPage";
import { SettingsPage } from "../pages/SettingsPage";

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/workflows" element={<WorkflowCatalogPage />} />
        <Route path="/workflows/access" element={<AccessRequestPage />} />
        <Route path="/workflows/procurement" element={<ProcurementRequestPage />} />
        <Route path="/workflows/maintenance" element={<MaintenanceRequestPage />} />
        <Route path="/runs" element={<SessionRunsPage />} />
        <Route path="/runs/:runId" element={<RunDetailPage />} />
        <Route path="/runs/:runId/approvals" element={<RunApprovalsPage />} />
        <Route path="/runs/:runId/tool-calls" element={<RunToolCallsPage />} />
        <Route path="/runs/:runId/audit" element={<RunAuditTrailPage />} />
        <Route path="/approvals" element={<SessionApprovalsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}
