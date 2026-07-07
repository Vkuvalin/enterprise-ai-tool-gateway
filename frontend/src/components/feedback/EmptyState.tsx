type EmptyStateProps = {
  title: string;
  detail?: string;
};

export function EmptyState({ title, detail }: EmptyStateProps) {
  return (
    <div className="state-box state-box--empty">
      <strong>{title}</strong>
      {detail ? <span>{detail}</span> : null}
    </div>
  );
}
