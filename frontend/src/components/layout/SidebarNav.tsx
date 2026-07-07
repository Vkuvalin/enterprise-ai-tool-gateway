import { Link, useLocation } from "react-router-dom";
import { useKnownRuns } from "../../state/knownRuns";

type SidebarSection = "dashboard" | "workflows" | "runs" | "approvals" | "tool-calls" | "audit" | "settings";

type SidebarItem = {
  label: string;
  to: string;
  section: SidebarSection;
  disabledLabel?: string;
};

const baseItems: SidebarItem[] = [
  { label: "Dashboard", to: "/dashboard", section: "dashboard" },
  { label: "Workflows", to: "/workflows", section: "workflows" },
  { label: "Agent Runs", to: "/runs", section: "runs" },
  { label: "Approvals", to: "/approvals", section: "approvals" },
  { label: "Settings", to: "/settings", section: "settings" }
];

export function SidebarNav() {
  const { pathname } = useLocation();
  const { selectedRunId, knownRunIds } = useKnownRuns();
  const activeSection = getActiveSection(pathname);
  const currentRunId = getRunIdFromPath(pathname) ?? selectedRunId;
  const runScopedItems: SidebarItem[] = currentRunId
    ? [
        { label: "Tool Calls", to: `/runs/${encodeURIComponent(currentRunId)}/tool-calls`, section: "tool-calls" },
        { label: "Audit Trail", to: `/runs/${encodeURIComponent(currentRunId)}/audit`, section: "audit" }
      ]
    : [
        { label: "Tool Calls", to: "/dashboard", section: "tool-calls", disabledLabel: "Select a run" },
        { label: "Audit Trail", to: "/dashboard", section: "audit", disabledLabel: "Select a run" }
      ];

  return (
    <aside className="sidebar">
      <nav className="sidebar__nav" aria-label="Primary navigation">
        {[...baseItems.slice(0, 4), ...runScopedItems, ...baseItems.slice(4)].map((item) => (
          <Link
            key={`${item.label}-${item.to}`}
            className={`sidebar__link ${
              activeSection === item.section && !item.disabledLabel ? "sidebar__link--active" : ""
            }`.trim()}
            to={item.to}
            title={item.disabledLabel ?? item.label}
          >
            <span>{item.label}</span>
            {item.disabledLabel ? <small>{item.disabledLabel}</small> : null}
          </Link>
        ))}
      </nav>
      <div className="sidebar__footer">
        <span>Known runs</span>
        <strong>{knownRunIds.length}</strong>
      </div>
    </aside>
  );
}

function getActiveSection(pathname: string): SidebarSection | null {
  if (pathname === "/dashboard" || pathname === "/") {
    return "dashboard";
  }
  if (pathname === "/workflows" || pathname.startsWith("/workflows/")) {
    return "workflows";
  }
  if (pathname === "/runs") {
    return "runs";
  }
  if (pathname === "/approvals" || /^\/runs\/[^/]+\/approvals$/.test(pathname)) {
    return "approvals";
  }
  if (/^\/runs\/[^/]+\/tool-calls$/.test(pathname)) {
    return "tool-calls";
  }
  if (/^\/runs\/[^/]+\/audit$/.test(pathname)) {
    return "audit";
  }
  if (/^\/runs\/[^/]+$/.test(pathname)) {
    return "runs";
  }
  if (pathname === "/settings") {
    return "settings";
  }
  return null;
}

function getRunIdFromPath(pathname: string): string | null {
  const match = /^\/runs\/([^/]+)/.exec(pathname);
  if (!match) {
    return null;
  }
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}
