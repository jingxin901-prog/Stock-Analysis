"use client";

import type { ReactNode } from "react";

import { useI18n } from "@/lib/i18n";

export function MetricCard({
  label,
  value,
  detail,
  tone = "neutral",
}: {
  label: string;
  value: string;
  detail?: string;
  tone?: "neutral" | "positive" | "negative" | "accent";
}) {
  return (
    <article className={`metric-card metric-${tone}`}>
      <div className="metric-card-top">
        <span className="metric-label">{label}</span>
        <span aria-hidden="true" className="metric-signal" />
      </div>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </article>
  );
}

export function Panel({
  title,
  eyebrow,
  action,
  children,
  className = "",
}: {
  title: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <div>
          {eyebrow ? <span className="panel-eyebrow">{eyebrow}</span> : null}
          <h2>{title}</h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function LoadingState({ label = "Loading research data" }: { label?: string }) {
  const { t } = useI18n();
  return (
    <div className="loading-state" role="status">
      <div className="loading-orbit"><span /></div>
      <strong>{label}</strong>
      <p>{t("common.loadingDetail")}</p>
    </div>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  const { t } = useI18n();
  return (
    <div className="error-banner" role="alert">
      <strong>{t("common.errorTitle")}</strong>
      <span>{message}</span>
    </div>
  );
}

export function ResearchNotice({ children }: { children: ReactNode }) {
  return (
    <div className="research-notice">
      <span aria-hidden="true"><svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="7" /><path d="M10 9v5m0-8v.2" /></svg></span>
      <p>{children}</p>
    </div>
  );
}
