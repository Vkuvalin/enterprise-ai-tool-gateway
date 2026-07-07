type JsonViewerProps = {
  value: unknown;
  label?: string;
};

export function JsonViewer({ value, label }: JsonViewerProps) {
  return (
    <div className="json-viewer">
      {label ? <div className="json-viewer__label">{label}</div> : null}
      <pre>{JSON.stringify(value ?? null, null, 2)}</pre>
    </div>
  );
}
