import type { Tone } from "./statusPresentation";

type StatusChipProps = {
  label: string;
  tone?: Tone;
  title?: string;
};

export function StatusChip({ label, tone = "gray", title }: StatusChipProps) {
  return (
    <span className={`status-chip status-chip--${tone}`} title={title}>
      {label}
    </span>
  );
}
