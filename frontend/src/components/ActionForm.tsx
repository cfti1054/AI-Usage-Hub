"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";
import type { ActionResult } from "@/app/actions";

type Action = (prev: ActionResult | null, fd: FormData) => Promise<ActionResult>;

export function ActionForm({
  action,
  children,
  className,
}: {
  action: Action;
  children: React.ReactNode;
  className?: string;
}) {
  const [state, formAction] = useActionState(action, null);
  return (
    <form action={formAction} className={className}>
      {children}
      {state && (
        <p className={`text-xs ${state.ok ? "text-emerald-600" : "text-rose-600"}`} role="status">
          {state.message}
        </p>
      )}
    </form>
  );
}

export function SubmitButton({
  children,
  variant = "primary",
}: {
  children: React.ReactNode;
  variant?: "primary" | "secondary" | "danger";
}) {
  const { pending } = useFormStatus();
  const styles = {
    primary: "bg-slate-900 text-white hover:bg-slate-700",
    secondary: "border border-slate-300 bg-white hover:bg-slate-100",
    danger: "border border-rose-300 bg-white text-rose-700 hover:bg-rose-50",
  }[variant];
  return (
    <button
      type="submit"
      disabled={pending}
      className={`rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50 ${styles}`}
    >
      {pending ? "처리 중…" : children}
    </button>
  );
}
