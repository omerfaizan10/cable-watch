export default function PageHead({
  kicker,
  title,
  children,
}: {
  kicker: string;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <header className="title-block page-head">
      <p className="kicker">{kicker}</p>
      <h1>{title}</h1>
      {children && <div className="standfirst">{children}</div>}
    </header>
  );
}
