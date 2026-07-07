import type { ToolCallResponse } from "../../api/types";
import { DataTable, type DataTableColumn } from "../../components/data/DataTable";
import { JsonViewer } from "../../components/data/JsonViewer";
import { StatusChip } from "../../components/status/StatusChip";

type ToolCallsTableProps = {
  toolCalls: ToolCallResponse[];
};

const columns: DataTableColumn<ToolCallResponse>[] = [
  {
    key: "tool",
    header: "Tool",
    render: (row) => (
      <div className="stack">
        <code>{row.tool_name}</code>
        <span>{row.tool_type}</span>
      </div>
    )
  },
  {
    key: "status",
    header: "Status",
    render: (row) => <StatusChip label={row.status} tone={row.status === "SUCCEEDED" ? "green" : "gray"} />
  },
  {
    key: "approval",
    header: "Approval",
    render: (row) =>
      row.requires_approval ? (
        <div className="stack">
          <StatusChip label="required" tone="yellow" />
          <code>{row.approval_id ?? "no approval id"}</code>
        </div>
      ) : (
        <StatusChip label="not required" tone="gray" />
      )
  },
  {
    key: "timestamps",
    header: "Created / Updated",
    render: (row) => (
      <div className="stack">
        <time>{row.created_at}</time>
        <time>{row.updated_at}</time>
      </div>
    )
  },
  {
    key: "error",
    header: "Safe error",
    render: (row) => row.error_message ?? "none"
  }
];

export function ToolCallsTable({ toolCalls }: ToolCallsTableProps) {
  return (
    <div className="stack stack--large">
      <DataTable
        columns={columns}
        rows={toolCalls}
        rowKey={(row) => row.id}
        emptyLabel="No tool calls recorded for this run."
      />
      {toolCalls.map((toolCall) => (
        <section className="panel" key={`${toolCall.id}-payloads`}>
          <h2>{toolCall.tool_name}</h2>
          <div className="two-column-grid">
            <JsonViewer value={toolCall.input_payload} label="Input payload" />
            <JsonViewer value={toolCall.output_payload} label="Output payload" />
          </div>
        </section>
      ))}
    </div>
  );
}
