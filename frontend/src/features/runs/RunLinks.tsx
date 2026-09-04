import { Link } from "react-router-dom";
import { useLocale } from "../../i18n/LocaleProvider";

type RunLinksProps = {
  runId: string;
  showDetailLink?: boolean;
};

export function RunLinks({ runId, showDetailLink = true }: RunLinksProps) {
  const { t } = useLocale();
  return (
    <div className="run-links">
      {showDetailLink ? <Link to={`/runs/${runId}`}>{t("runLinks.detail")}</Link> : null}
      <Link to={`/runs/${runId}/approvals`}>{t("common.approvals")}</Link>
      <Link to={`/runs/${runId}/tool-calls`}>{t("common.toolCalls")}</Link>
      <Link to={`/runs/${runId}/audit`}>{t("common.auditTrail")}</Link>
    </div>
  );
}
