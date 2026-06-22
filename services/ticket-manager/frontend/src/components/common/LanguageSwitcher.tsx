import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

const LANGS = ["en", "ru", "es"] as const;
type Lang = (typeof LANGS)[number];

export function LanguageSwitcher() {
  const { i18n, t } = useTranslation();
  const current = i18n.language as Lang;

  function handleChange(lang: Lang) {
    i18n.changeLanguage(lang);
    localStorage.setItem("lang", lang);
  }

  return (
    <div className="flex border border-border rounded overflow-hidden" role="group" aria-label={t("language.label")}>
      {LANGS.map((lang) => (
        <button
          key={lang}
          onClick={() => handleChange(lang)}
          aria-pressed={current === lang}
          className={cn(
            "px-2 py-1 text-xs font-medium border-r border-border last:border-r-0 transition-colors",
            current === lang
              ? "bg-background text-primary font-bold"
              : "bg-card text-muted-foreground hover:bg-muted"
          )}
        >
          {t(`language.${lang}`)}
        </button>
      ))}
    </div>
  );
}
