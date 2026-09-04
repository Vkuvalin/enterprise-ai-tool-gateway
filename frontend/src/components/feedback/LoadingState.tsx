import { useLocale } from "../../i18n/LocaleProvider";

type LoadingStateProps = {
  label?: string;
};

export function LoadingState({ label }: LoadingStateProps) {
  const { t } = useLocale();
  return <div className="state-box state-box--loading">{label ?? t("common.loading")}</div>;
}
