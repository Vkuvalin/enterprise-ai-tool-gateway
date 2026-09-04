import { useState } from "react";
import type { AuditEventResponse } from "../../api/types";
import { DataTable, type DataTableColumn } from "../../components/data/DataTable";
import { InspectorPanel } from "../../components/data/InspectorPanel";
import { JsonViewer } from "../../components/data/JsonViewer";
import { useLocale } from "../../i18n/LocaleProvider";

type AuditTimelineProps = {
  events: AuditEventResponse[];
};

export function AuditTimeline({ events }: AuditTimelineProps) {
  const { t } = useLocale();
  const sorted = [...events].sort((left, right) => left.created_at.localeCompare(right.created_at));
  const [selectedId, setSelectedId] = useState(sorted[0]?.id ?? null);
  const selected = sorted.find((event) => event.id === selectedId) ?? sorted[0] ?? null;
  const columns: DataTableColumn<AuditEventResponse>[] = [
    { key: "created", header: t("audit.created"), render: (row) => <time>{row.created_at}</time> },
    { key: "type", header: t("audit.eventType"), render: (row) => <code>{row.event_type}</code> },
    { key: "actor", header: t("common.actor"), render: (row) => row.actor },
    { key: "id", header: t("audit.eventId"), render: (row) => <code>{row.id}</code> }
  ];

  return (
    <div className="content-with-inspector">
      <div className="panel">
        <DataTable
          columns={[
            ...columns,
            {
              key: "select",
              header: t("common.inspect"),
              render: (row) => (
                <button className="ghost-button" type="button" onClick={() => setSelectedId(row.id)}>
                  {t("common.select")}
                </button>
              )
            }
          ]}
          rows={sorted}
          rowKey={(row) => row.id}
          emptyLabel={t("audit.empty")}
        />
      </div>
      <InspectorPanel title={t("audit.selected")}>
        {selected ? (
          <div className="stack">
            <div className="kv-grid">
              <span>{t("common.eventType")}</span>
              <code>{selected.event_type}</code>
              <span>{t("common.actor")}</span>
              <span>{selected.actor}</span>
              <span>{t("common.created")}</span>
              <time>{selected.created_at}</time>
            </div>
            <JsonViewer value={selected.payload} label={t("common.payload")} />
          </div>
        ) : (
          <p className="muted">{t("audit.selectPrompt")}</p>
        )}
      </InspectorPanel>
    </div>
  );
}
