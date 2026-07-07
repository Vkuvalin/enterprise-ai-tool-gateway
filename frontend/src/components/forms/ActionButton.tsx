import type { ButtonHTMLAttributes, ReactNode } from "react";

type ActionButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "success";
  children: ReactNode;
};

export function ActionButton({
  variant = "secondary",
  children,
  className = "",
  ...props
}: ActionButtonProps) {
  return (
    <button className={`action-button action-button--${variant} ${className}`.trim()} {...props}>
      {children}
    </button>
  );
}
