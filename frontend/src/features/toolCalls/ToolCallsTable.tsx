import type { ToolCallResponse } from "../../api/types";
import { DataTable, type DataTableColumn } from "../../components/data/DataTable";
import { JsonViewer } from "../../components/data/JsonViewer";
import { StatusChip } from "../../components/status/StatusChip";
import { useLocale } from "../../i18n/LocaleProvider";
import { getToolCallStatusLabel } from "../../i18n/presentation";

type ToolCallsTableProps = {
  toolCalls: ToolCallResponse[];
};

export function ToolCallsTable({ toolCalls }: ToolCallsTableProps) {
  const { t } = useLocale();
  const columns: DataTableColumn<ToolCallResponse>[] = [
    {
      key: "tool",
      header: t("toolCalls.tool"),
      render: (row) => (
        <div className="stack">
          <code>{row.tool_name}</code>
          <span>{row.tool_type}</span>
        </div>
      )
    },
    {
      key: "status",
      header: t("common.status"),
      render: (row) => (
        <StatusChip label={getToolCallStatusLabel(row.status, t)} tone={row.status === "SUCCEEDED" ? "green" : "gray"} />
      )
    },
    {
      key: "approval",
      header: t("toolCalls.approval"),
      render: (row) =>
        row.requires_approval ? (
          <div className="stack">
            <StatusChip label={t("common.required")} tone="yellow" />
            <code>{row.approval_id ?? t("common.noApprovalId")}</code>
          </div>
        ) : (
          <StatusChip label={t("common.notRequired")} tone="gray" />
        )
    },
    {
      key: "timestamps",
      header: t("toolCalls.createdUpdated"),
      render: (row) => (
        <div className="stack">
          <time>{row.created_at}</time>
          <time>{row.updated_at}</time>
        </div>
      )
    },
    {
      key: "error",
      header: t("toolCalls.safeError"),
      render: (row) => row.error_message ?? t("common.none")
    }
  ];

  return (
    <div className="stack stack--large">
      <DataTable
        columns={columns}
        rows={toolCalls}
        rowKey={(row) => row.id}
        emptyLabel={t("toolCalls.empty")}
      />
      {toolCalls.map((toolCall) => (
        <section className="panel" key={`${toolCall.id}-payloads`}>
          <h2>{toolCall.tool_name}</h2>
          <div className="two-column-grid">
            <JsonViewer value={toolCall.input_payload} label={t("common.inputPayload")} />
            <JsonViewer value={toolCall.output_payload} label={t("common.outputPayload")} />
          </div>
        </section>
      ))}
    </div>
  );
}
