import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import type { AdminUserResponse, AdminUserCreate, AdminUserUpdate, UserRole } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface UserFormProps {
  user?: AdminUserResponse;
  onSubmit: (data: AdminUserCreate | AdminUserUpdate) => Promise<void>;
  onCancel: () => void;
}

const ROLES: UserRole[] = ["user", "administrator"];

export function UserForm({ user, onSubmit, onCancel }: UserFormProps) {
  const { t } = useTranslation();
  const isEdit = !!user;

  const [email, setEmail] = useState(user?.email ?? "");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>(user?.role ?? "user");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!email.trim()) { setError(t("admin.users.form.emailRequired")); return; }
    if (!isEdit && password.length < 8) { setError(t("admin.users.form.passwordRequired")); return; }
    setLoading(true);
    try {
      if (isEdit) {
        const payload: AdminUserUpdate = {};
        if (email !== user!.email) payload.email = email.trim();
        if (role !== user!.role) payload.role = role;
        await onSubmit(payload);
      } else {
        await onSubmit({ email: email.trim(), password, role });
      }
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e.response?.data?.detail ?? t(isEdit ? "admin.users.errors.updateFailed" : "admin.users.errors.createFailed"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="w-full max-w-[95vw] sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? t("admin.users.form.editTitle") : t("admin.users.form.createTitle")}</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} noValidate className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="user-email">
              {t("admin.users.form.email")} <span className="text-destructive">*</span>
            </Label>
            <Input
              id="user-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={loading}
              autoComplete="off"
            />
          </div>

          {!isEdit && (
            <div className="space-y-2">
              <Label htmlFor="user-password">
                {t("admin.users.form.password")} <span className="text-destructive">*</span>
              </Label>
              <Input
                id="user-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
                autoComplete="new-password"
                minLength={8}
              />
              <span className="text-xs text-muted-foreground">{t("admin.users.form.passwordHint")}</span>
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="user-role">{t("admin.users.form.role")}</Label>
            <Select value={role} onValueChange={(v) => setRole(v as UserRole)} disabled={loading}>
              <SelectTrigger id="user-role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROLES.map((r) => (
                  <SelectItem key={r} value={r}>{t(`admin.users.role.${r}`)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

          <div className="flex gap-2 justify-end pt-2">
            <Button type="button" variant="outline" onClick={onCancel} disabled={loading}>
              {t("admin.users.form.cancel")}
            </Button>
            <Button type="submit" disabled={loading}>
              {loading
                ? (isEdit ? t("admin.users.form.saving") : t("admin.users.form.creating"))
                : (isEdit ? t("admin.users.form.save") : t("admin.users.form.create"))}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
