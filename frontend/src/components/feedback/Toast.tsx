import { useCallback, useEffect, useRef, useState } from "react";
import { useLocale } from "../../i18n/LocaleProvider";
import type { MessageKey } from "../../i18n/messages";

type ToastTone = "success" | "error" | "info";

export type ToastState = ({ message: string; messageKey?: never } | { message?: never; messageKey: MessageKey }) & {
  tone?: ToastTone;
};

export function useToast(timeoutMs = 1600) {
  const [toast, setToast] = useState<ToastState | null>(null);
  const timeoutRef = useRef<number | null>(null);

  const clearToast = useCallback(() => {
    if (timeoutRef.current !== null) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    setToast(null);
  }, []);

  const showToast = useCallback(
    (nextToast: ToastState) => {
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
      }
      setToast(nextToast);
      timeoutRef.current = window.setTimeout(() => {
        setToast(null);
        timeoutRef.current = null;
      }, timeoutMs);
    },
    [timeoutMs]
  );

  useEffect(() => {
    return () => {
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return { toast, showToast, clearToast };
}

type ToastProps = {
  toast: ToastState | null;
};

export function Toast({ toast }: ToastProps) {
  const { t } = useLocale();
  if (!toast) {
    return null;
  }

  return (
    <div className={`toast toast--${toast.tone ?? "info"}`} role={toast.tone === "error" ? "alert" : "status"}>
      {toast.messageKey ? t(toast.messageKey) : toast.message}
    </div>
  );
}
