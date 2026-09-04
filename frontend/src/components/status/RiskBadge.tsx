import { StatusChip } from "./StatusChip";
import { toneForRisk } from "./statusPresentation";
import { useLocale } from "../../i18n/LocaleProvider";
import { getRiskLabel } from "../../i18n/presentation";

type RiskBadgeProps = {
  risk: string | null | undefined;
};

export function RiskBadge({ risk }: RiskBadgeProps) {
  const { t } = useLocale();
  return <StatusChip label={getRiskLabel(risk, t)} tone={toneForRisk(risk)} />;
}
