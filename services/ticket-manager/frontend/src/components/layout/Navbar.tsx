import { useState } from "react";
import { Link } from "react-router-dom";
import { Sun, Moon, LogOut, Menu } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { LanguageSwitcher } from "@/components/common/LanguageSwitcher";
import { useAuthStore } from "@/store/auth";
import { useTheme } from "@/hooks/useTheme";

export function Navbar() {
  const { t } = useTranslation();
  const { theme, setTheme } = useTheme();
  const { currentUser, logout } = useAuthStore((s) => ({
    currentUser: s.currentUser,
    logout: s.logout,
  }));
  const [mobileOpen, setMobileOpen] = useState(false);

  const isDark = theme === "dark";

  function toggleDark() {
    setTheme(isDark ? "light" : "dark");
  }

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto max-w-7xl px-4 flex h-14 items-center gap-4">
        {/* Mobile hamburger */}
        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" className="md:hidden" aria-label={t("nav.openMenu")}>
              <Menu className="h-5 w-5" />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-64">
            <SheetHeader>
              <SheetTitle className="text-left">Ticket Manager</SheetTitle>
            </SheetHeader>
            <nav className="flex flex-col gap-1 mt-4">
              <Button variant="ghost" size="sm" asChild className="justify-start" onClick={() => setMobileOpen(false)}>
                <Link to="/projects">{t("nav.projects")}</Link>
              </Button>
              {currentUser?.role === "administrator" && (
                <Button variant="ghost" size="sm" asChild className="justify-start" onClick={() => setMobileOpen(false)}>
                  <Link to="/admin/users">{t("nav.admin")}</Link>
                </Button>
              )}
            </nav>
            <div className="mt-4">
              <LanguageSwitcher />
            </div>
          </SheetContent>
        </Sheet>

        <span className="text-xl font-semibold text-foreground mr-4">Ticket Manager</span>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-1">
          <Button variant="ghost" size="sm" asChild>
            <Link to="/projects">{t("nav.projects")}</Link>
          </Button>
          {currentUser?.role === "administrator" && (
            <Button variant="ghost" size="sm" asChild>
              <Link to="/admin/users">{t("nav.admin")}</Link>
            </Button>
          )}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <div className="hidden md:block">
            <LanguageSwitcher />
          </div>

          <Button
            variant="ghost"
            size="icon"
            onClick={toggleDark}
            aria-label={t("theme.toggleDark")}
          >
            {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>

          {currentUser && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" className="max-w-[180px] truncate">
                  {currentUser.email}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={logout} className="text-destructive focus:text-destructive">
                  <LogOut className="h-4 w-4 mr-2" />
                  {t("auth.logout")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>
    </header>
  );
}
