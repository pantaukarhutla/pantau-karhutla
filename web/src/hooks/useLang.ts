import { useCallback, useState } from "react";
import type { Lang } from "../i18n";
import { usePersistentState } from "./usePersistentState";

const LANG_KEY = "haze.lang";

/** Browser default: Bahasa for Indonesian (and Malay) locales, else English. */
export function browserLang(): Lang {
  const langs = navigator.languages?.length ? navigator.languages : [navigator.language];
  return langs.some((l) => /^(id|in|ms)\b/i.test(l)) ? "id" : "en";
}

export const parseLang = (v: string | null): Lang | null => (v === "id" || v === "en" ? v : null);
const asStored = (l: Lang) => l;

/**
 * Language: a link's ?lang= > the visitor's own earlier choice > browser
 * locale. Only the visitor's own choice is remembered.
 */
export function useLang(fromLink: Lang | null): [Lang, (l: Lang) => void] {
  const [saved, save] = usePersistentState<Lang>(LANG_KEY, browserLang(), parseLang, asStored);
  const [link, setLink] = useState(fromLink);
  const choose = useCallback(
    (l: Lang) => {
      setLink(null);
      save(l);
    },
    [save],
  );
  return [link ?? saved, choose];
}
