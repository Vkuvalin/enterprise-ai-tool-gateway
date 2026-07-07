import { StatusChip } from "./StatusChip";
import { toneForRisk } from "./statusPresentation";

type RiskBadgeProps = {
  risk: string | null | undefined;
};

export function RiskBadge({ risk }: RiskBadgeProps) {
  return <StatusChip label={risk ?? "Unknown risk"} tone={toneForRisk(risk)} />;
}
