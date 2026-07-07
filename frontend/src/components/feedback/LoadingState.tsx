type LoadingStateProps = {
  label?: string;
};

export function LoadingState({ label = "Loading..." }: LoadingStateProps) {
  return <div className="state-box state-box--loading">{label}</div>;
}
