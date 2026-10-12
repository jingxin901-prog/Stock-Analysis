export function PageHeader({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <header className="page-header">
      <div className="page-header-copy">
        <div className="eyebrow"><span />{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div aria-hidden="true" className="page-header-mark">
        <span>QAI / RESEARCH SYSTEM</span>
        <small>MODEL / CONDITIONAL</small>
        <i />
      </div>
    </header>
  );
}
