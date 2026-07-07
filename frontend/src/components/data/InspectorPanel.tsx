import type { ReactNode } from "react";

type InspectorPanelProps = {
  title: string;
  children: ReactNode;
  actions?: ReactNode;
};

export function InspectorPanel({ title, children, actions }: InspectorPanelProps) {
  return (
    <aside className="inspector-panel">
      <div className="inspector-panel__header">
        <h2>{title}</h2>
        {actions ? <div>{actions}</div> : null}
      </div>
      <div className="inspector-panel__body">{children}</div>
    </aside>
  );
}
