import { useTranslation } from "react-i18next";
import { useTheme, type ThemeKey } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";

const THEMES: { key: ThemeKey; swatch: string }[] = [
  { key: "light", swatch: "#ffffff" },
  { key: "dark", swatch: "#1a1a2e" },
  { key: "solarized", swatch: "#fdf6e3" },
  { key: "oceanic", swatch: "#1b2b34" },
  { key: "high-contrast", swatch: "#000000" },
  { key: "warm", swatch: "#faf0e6" },
];

export function ThemeSwitcher() {
  const { t } = useTranslation();
  const { theme, setTheme } = useTheme();

  return (
    <div className="flex gap-1 items-center" role="group" aria-label={t("theme.label")}>
      {THEMES.map(({ key, swatch }) => (
        <button
          key={key}
          onClick={() => setTheme(key)}
          title={t(`theme.themes.${key}`)}
          aria-pressed={theme === key}
          className={cn(
            "h-5 w-5 rounded-full border border-border cursor-pointer p-0 flex-shrink-0 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            theme === key ? "ring-2 ring-primary ring-offset-2" : ""
          )}
          style={{ background: swatch }} // swatch-color-required
        />
      ))}
    </div>
  );
}
