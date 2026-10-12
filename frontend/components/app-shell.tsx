"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useI18n } from "@/lib/i18n";

type NavigationIcon = "market" | "stock" | "portfolio";

function NavIcon({ icon }: { icon: NavigationIcon }) {
  if (icon === "market") {
    return <svg aria-hidden="true" viewBox="0 0 20 20"><path d="M3 15.5V11m4.7 4.5V7.5m4.6 8V4.5m4.7 11V9" /></svg>;
  }
  if (icon === "stock") {
    return <svg aria-hidden="true" viewBox="0 0 20 20"><path d="m2.8 13.8 4-4 3.2 2.5 6.9-7" /><path d="M13.3 5.3h3.6v3.6" /></svg>;
  }
  return <svg aria-hidden="true" viewBox="0 0 20 20"><path d="M10 2.5v7.6h7.5A7.5 7.5 0 1 1 10 2.5Z" /><path d="M12.6 2.9a5.7 5.7 0 0 1 4.5 4.5h-4.5V2.9Z" /></svg>;
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { locale, setLocale, t } = useI18n();
  const navigation = [
    { href: "/market-overview", label: t("nav.market"), code: "01", icon: "market" as const },
    { href: "/stock-analysis", label: t("nav.stock"), code: "02", icon: "stock" as const },
    { href: "/portfolio-optimizer", label: t("nav.portfolio"), code: "03", icon: "portfolio" as const },
  ];
  const activeNavigation = navigation.find((item) => pathname === item.href) ?? navigation[0];

  return (
    <div className="app-frame">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark">Q</div>
          <div>
            <div className="brand-name">QuantAI</div>
            <div className="brand-kicker">{t("brand.subtitle")}</div>
          </div>
          <span className="brand-badge">SYS</span>
        </div>

        <div className="language-switch" aria-label={t("language.label")}>
          <button className={locale === "en" ? "lang-active" : ""} onClick={() => setLocale("en")} type="button">{t("language.en")}</button>
          <button className={locale === "zh" ? "lang-active" : ""} onClick={() => setLocale("zh")} type="button">{t("language.zh")}</button>
        </div>

        <div className="nav-label">{t("nav.label")}</div>
        <nav className="nav-list" aria-label="Primary navigation">
          {navigation.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                className={`nav-item ${active ? "nav-item-active" : ""}`}
                href={item.href}
                key={item.href}
              >
                <span className="nav-icon"><NavIcon icon={item.icon} /></span>
                <span className="nav-copy"><small>{item.code}</small>{item.label}</span>
                <span className="nav-arrow">↗</span>
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-note">
          <span className="status-dot" />
          <div>
            <strong>{t("shell.environment")}</strong>
            <p>{t("shell.disclaimer")}</p>
          </div>
        </div>
      </aside>

      <main className="main-panel">
        <div className="workspace-bar">
          <div className="workspace-context">
            <span>{t("shell.workspace")}</span>
            <strong>{activeNavigation.label}</strong>
          </div>
          <div className="terminal-feed">
            <div className="terminal-feed-item"><small>{t("shell.feed")}</small><strong>YAHOO / EOD</strong></div>
            <div className="terminal-feed-item"><small>{t("shell.mode")}</small><strong>{t("shell.historical")}</strong></div>
            <div className="workspace-status">
              <span className="status-dot" />
              <span>{t("shell.environment")}</span>
            </div>
          </div>
        </div>
        <div className="mobile-brand">
          <div className="mobile-brand-copy">
            <div className="brand-mark">Q</div>
            <div><strong>QuantAI</strong><small>{activeNavigation.label}</small></div>
          </div>
          <div className="language-switch mobile-language" aria-label={t("language.label")}>
            <button className={locale === "en" ? "lang-active" : ""} onClick={() => setLocale("en")} type="button">EN</button>
            <button className={locale === "zh" ? "lang-active" : ""} onClick={() => setLocale("zh")} type="button">中文</button>
          </div>
        </div>
        <div className="content-wrap">{children}</div>
        <footer className="footer">
          <span>{t("shell.footerLeft")}</span>
          <span>{t("shell.footerRight")}</span>
        </footer>
      </main>
    </div>
  );
}
