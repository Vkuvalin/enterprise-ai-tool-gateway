import { Outlet } from "react-router-dom";
import { SidebarNav } from "../components/layout/SidebarNav";
import { TopStatusBar } from "../components/layout/TopStatusBar";

export function AppShell() {
  return (
    <div className="app-shell">
      <TopStatusBar />
      <div className="app-shell__body">
        <SidebarNav />
        <main className="app-shell__main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
