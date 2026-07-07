import { apiBaseUrl } from "../../api/client";
import { useApiStatus } from "../../features/capabilities/useApiStatus";
import { Toast, useToast } from "../feedback/Toast";
import { StatusChip } from "../status/StatusChip";

export function TopStatusBar() {
  const { toast, showToast } = useToast();
  const { health, capabilities, loading, hasLoaded, error, refresh } = useApiStatus({
    onRefreshSuccess: () => showToast({ message: "Data refreshed", tone: "success" }),
    onRefreshError: () => showToast({ message: "Refresh failed", tone: "error" })
  });
  const initialLoading = loading && !hasLoaded;

  return (
    <>
      <header className="top-status-bar">
        <div className="top-status-bar__brand">
          <span className="brand-mark">EA</span>
          <span>Enterprise AI Tool Gateway</span>
        </div>
        <div className="top-status-bar__badges">
          <StatusChip label="local/demo" tone="blue" />
          <StatusChip
            label={`provider: ${capabilities?.provider_mode ?? "unknown"}`}
            tone={capabilities?.provider_mode === "mock" ? "purple" : "gray"}
          />
          <StatusChip
            label={initialLoading ? "API checking" : error ? "API unavailable" : `API ${health?.status ?? "unknown"}`}
            tone={error ? "red" : health?.status === "ok" ? "green" : "gray"}
          />
          <StatusChip label="DB: SQLite" tone="gray" />
          <StatusChip
            label={`model selector: ${capabilities?.model_selection.enabled ? "enabled" : "disabled"}`}
            tone={capabilities?.model_selection.enabled ? "orange" : "gray"}
          />
        </div>
        <div className="top-status-bar__right">
          <code>{apiBaseUrl}</code>
          <button className="ghost-button" type="button" onClick={refresh}>
            Refresh
          </button>
        </div>
      </header>
      <Toast toast={toast} />
    </>
  );
}
