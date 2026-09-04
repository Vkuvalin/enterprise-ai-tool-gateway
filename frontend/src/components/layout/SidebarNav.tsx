import { Link, useLocation } from "react-router-dom";
import { useLocale } from "../../i18n/LocaleProvider";
import type { MessageKey } from "../../i18n/messages";
import { useKnownRuns } from "../../state/knownRuns";

type SidebarSection = "dashboard" | "workflows" | "runs" | "approvals" | "tool-calls" | "audit" | "settings";

type SidebarItem = {
  labelKey: MessageKey;
  to: string;
  section: SidebarSection;
  disabledLabelKey?: MessageKey;
};

const baseItems: SidebarItem[] = [
  { labelKey: "nav.dashboard", to: "/dashboard", section: "dashboard" },
  { labelKey: "nav.workflows", to: "/workflows", section: "workflows" },
  { labelKey: "nav.runs", to: "/runs", section: "runs" },
  { labelKey: "nav.approvals", to: "/approvals", section: "approvals" },
  { labelKey: "nav.settings", to: "/settings", section: "settings" }
];

export function SidebarNav() {
  const { t } = useLocale();
  const { pathname } = useLocation();
  const { selectedRunId, knownRunIds } = useKnownRuns();
  const activeSection = getActiveSection(pathname);
  const currentRunId = getRunIdFromPath(pathname) ?? selectedRunId;
  const runScopedItems: SidebarItem[] = currentRunId
    ? [
        { labelKey: "nav.toolCalls", to: `/runs/${encodeURIComponent(currentRunId)}/tool-calls`, section: "tool-calls" },
        { labelKey: "nav.auditTrail", to: `/runs/${encodeURIComponent(currentRunId)}/audit`, section: "audit" }
      ]
    : [
        { labelKey: "nav.toolCalls", to: "/dashboard", section: "tool-calls", disabledLabelKey: "nav.selectRun" },
        { labelKey: "nav.auditTrail", to: "/dashboard", section: "audit", disabledLabelKey: "nav.selectRun" }
      ];

  return (
    <aside className="sidebar">
      <nav className="sidebar__nav" aria-label={t("nav.primary")}>
        {[...baseItems.slice(0, 4), ...runScopedItems, ...baseItems.slice(4)].map((item) => (
          <Link
            key={`${item.section}-${item.to}`}
            className={`sidebar__link ${
              activeSection === item.section && !item.disabledLabelKey ? "sidebar__link--active" : ""
            }`.trim()}
            to={item.to}
            title={item.disabledLabelKey ? t(item.disabledLabelKey) : t(item.labelKey)}
          >
            <span>{t(item.labelKey)}</span>
            {item.disabledLabelKey ? <small>{t(item.disabledLabelKey)}</small> : null}
          </Link>
        ))}
      </nav>
      <div className="sidebar__footer">
        <span>{t("nav.knownRuns")}</span>
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
