import type { ReactNode } from "react";

type MetricCardProps = {
  label: string;
  value: ReactNode;
  helper?: ReactNode;
  tone?: "default" | "good" | "warn" | "danger" | "info";
};

export function MetricCard({ label, value, helper, tone = "default" }: MetricCardProps) {
  return (
    <section className={`metric-card metric-card--${tone}`}>
      <div className="metric-card__label">{label}</div>
      <div className="metric-card__value">{value}</div>
      {helper ? <div className="metric-card__helper">{helper}</div> : null}
    </section>
  );
}
