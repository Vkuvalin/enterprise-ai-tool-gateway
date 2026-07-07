import { useCallback, useEffect, useRef, useState } from "react";

type ToastTone = "success" | "error" | "info";

export type ToastState = {
  message: string;
  tone?: ToastTone;
};

export function useToast(timeoutMs = 1600) {
  const [toast, setToast] = useState<ToastState | null>(null);
  const timeoutRef = useRef<number | null>(null);

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

  return { toast, showToast };
}

type ToastProps = {
  toast: ToastState | null;
};

export function Toast({ toast }: ToastProps) {
  if (!toast) {
    return null;
  }

  return (
    <div className={`toast toast--${toast.tone ?? "info"}`} role={toast.tone === "error" ? "alert" : "status"}>
      {toast.message}
    </div>
  );
}
