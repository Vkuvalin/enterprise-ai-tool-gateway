import { useState } from "react";
import type { AuditEventResponse } from "../../api/types";
import { DataTable, type DataTableColumn } from "../../components/data/DataTable";
import { InspectorPanel } from "../../components/data/InspectorPanel";
import { JsonViewer } from "../../components/data/JsonViewer";

type AuditTimelineProps = {
  events: AuditEventResponse[];
};

const columns: DataTableColumn<AuditEventResponse>[] = [
  { key: "created", header: "Created", render: (row) => <time>{row.created_at}</time> },
  { key: "type", header: "Event Type", render: (row) => <code>{row.event_type}</code> },
  { key: "actor", header: "Actor", render: (row) => row.actor },
  { key: "id", header: "Event ID", render: (row) => <code>{row.id}</code> }
];

export function AuditTimeline({ events }: AuditTimelineProps) {
  const sorted = [...events].sort((left, right) => left.created_at.localeCompare(right.created_at));
  const [selectedId, setSelectedId] = useState(sorted[0]?.id ?? null);
  const selected = sorted.find((event) => event.id === selectedId) ?? sorted[0] ?? null;

  return (
    <div className="content-with-inspector">
      <div className="panel">
        <DataTable
          columns={[
            ...columns,
            {
              key: "select",
              header: "Inspect",
              render: (row) => (
                <button className="ghost-button" type="button" onClick={() => setSelectedId(row.id)}>
                  Select
                </button>
              )
            }
          ]}
          rows={sorted}
          rowKey={(row) => row.id}
          emptyLabel="No audit events recorded for this run."
        />
      </div>
      <InspectorPanel title="Selected Event">
        {selected ? (
          <div className="stack">
            <div className="kv-grid">
              <span>Event type</span>
              <code>{selected.event_type}</code>
              <span>Actor</span>
              <span>{selected.actor}</span>
              <span>Created</span>
              <time>{selected.created_at}</time>
            </div>
            <JsonViewer value={selected.payload} label="Payload" />
          </div>
        ) : (
          <p className="muted">Select an event to inspect the payload.</p>
        )}
      </InspectorPanel>
    </div>
  );
}
