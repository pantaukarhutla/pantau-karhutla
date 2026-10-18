// One sidebar card: a title with its methodology link, the headline, and the
// rest one tap away. Most readers need the headline; everything else stays
// reachable, never dropped.
import type { ReactNode } from "react";
import type { Strings } from "./i18n";
import { MethodLink } from "./Methodology";
import type { MethodId } from "./methodText";

interface Props {
  title: ReactNode;
  method?: MethodId;
  /** a small action beside the title (e.g. "show on map") */
  action?: ReactNode;
  className?: string;
  s: Strings;
  /** start folded: only the title and `lead` show until opened */
  folded?: boolean;
  /** the headline, shown even when folded */
  lead?: ReactNode;
  children?: ReactNode;
  /** secondary detail behind "Selengkapnya" */
  more?: ReactNode;
}

function Title({ title, method, action, s }: Pick<Props, "title" | "method" | "action" | "s">) {
  return (
    <h2>
      <span>
        {title} {method && <MethodLink id={method} s={s} />}
      </span>
      {/* An action in a folded card's header must not toggle the card. */}
      {action && <span onClick={(e) => e.preventDefault()}>{action}</span>}
    </h2>
  );
}

/** "Selengkapnya" / "Lebih sedikit" toggle around secondary detail. */
export function More({ s, children }: { s: Strings; children: ReactNode }) {
  return (
    <details className="more">
      <summary>
        <span className="more-open">{s.moreShow}</span>
        <span className="more-close">{s.moreHide}</span>
      </summary>
      {children}
    </details>
  );
}

export function Card({ title, method, action, className, s, folded, lead, children, more }: Props) {
  const body = (
    <>
      {children}
      {more && <More s={s}>{more}</More>}
    </>
  );
  if (folded) {
    return (
      <details className={`card folded ${className ?? ""}`}>
        <summary>
          <Title title={title} method={method} action={action} s={s} />
          {lead && <div className="card-lead">{lead}</div>}
        </summary>
        <div className="card-body">{body}</div>
      </details>
    );
  }
  return (
    <section className={`card ${className ?? ""}`}>
      <Title title={title} method={method} action={action} s={s} />
      {lead && <div className="card-lead">{lead}</div>}
      {body}
    </section>
  );
}
