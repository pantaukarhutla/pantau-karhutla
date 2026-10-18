// Methodology panel: how each number is made. Any card opens it at its own
// section with <MethodLink id="..." />; the panel lists every section.
import { createContext, useContext, useEffect, useRef } from "react";
import { METHOD_IDS, METHODS, type MethodId } from "./methodText";
import type { Lang, Strings } from "./i18n";
import { REPO_URL } from "./links";

const OpenMethod = createContext<(id: MethodId) => void>(() => {});
export const MethodProvider = OpenMethod.Provider;

/** Small "(i) how it's calculated" link next to a number or card title. */
export function MethodLink({ id, s }: { id: MethodId; s: Strings }) {
  const open = useContext(OpenMethod);
  return (
    <button
      className="method-link"
      // preventDefault: inside a folded card's header, opening the method must not also toggle the card
      onClick={(e) => {
        e.preventDefault();
        open(id);
      }}
      title={s.methodHint}
      aria-label={`${s.methodHint}: ${id}`}
    >
      ⓘ
    </button>
  );
}

export function MethodologyPanel({ at, lang, s, onClose, onPick }: { at: MethodId; lang: Lang; s: Strings; onClose: () => void; onPick: (id: MethodId) => void }) {
  const methods = METHODS[lang];
  const m = methods[at];
  const body = useRef<HTMLDivElement>(null);
  // Braces: newer browsers return a Promise from scrollTo, and an effect's
  // return value is taken as its cleanup ("destroy is not a function").
  useEffect(() => {
    body.current?.scrollTo({ top: 0 });
  }, [at]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="method-backdrop" onClick={onClose}>
      <div className="method-panel" role="dialog" aria-modal="true" aria-labelledby="method-title" onClick={(e) => e.stopPropagation()}>
        <nav className="method-nav" aria-label={s.methodTitle}>
          <div className="method-nav-title">{s.methodTitle}</div>
          {METHOD_IDS.map((id) => (
            <button key={id} className={id === at ? "on" : ""} onClick={() => onPick(id)}>
              {methods[id].title}
            </button>
          ))}
        </nav>
        <div className="method-body" ref={body}>
          <button className="close" onClick={onClose} aria-label={s.close}>
            ×
          </button>
          <h1 id="method-title">{m.title}</h1>
          <p className="method-what">{m.what}</p>
          <h2>{s.methodHow}</h2>
          <ol>
            {m.how.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ol>
          <h2>{s.methodData}</h2>
          <ul>
            {m.data.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
          {m.tested && (
            <>
              <h2>{s.methodTested}</h2>
              <ul>
                {m.tested.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </>
          )}
          <h2>{s.methodLimits}</h2>
          <ul>
            {m.limits.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
          <p className="note">
            {s.methodFooter}{" "}
            <a href={REPO_URL} target="_blank" rel="noopener">
              {REPO_URL.replace("https://", "")}
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
