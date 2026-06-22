import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/store/auth";
import { listAdminUsers, createAdminUser, updateAdminUser, blockAdminUser, unblockAdminUser } from "@/api/admin";
import { UserTable } from "@/components/admin/UserTable";
import { UserForm } from "@/components/admin/UserForm";
import type { AdminUserResponse, AdminUserCreate, AdminUserUpdate } from "@/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const QUERY_KEY = ["admin", "users"] as const;

export function AdminUsersPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const currentUser = useAuthStore((s) => s.currentUser);

  const [showForm, setShowForm] = useState(false);
  const [editingUser, setEditingUser] = useState<AdminUserResponse | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: QUERY_KEY,
    queryFn: listAdminUsers,
  });

  const createMutation = useMutation({
    mutationFn: (payload: AdminUserCreate) => createAdminUser(payload),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: QUERY_KEY }); setShowForm(false); },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: AdminUserUpdate }) => updateAdminUser(id, payload),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: QUERY_KEY }); setEditingUser(null); },
  });

  const blockMutation = useMutation({
    mutationFn: (userId: string) => blockAdminUser(userId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUERY_KEY }),
    onError: () => setActionError(t("admin.users.errors.blockFailed")),
  });

  const unblockMutation = useMutation({
    mutationFn: (userId: string) => unblockAdminUser(userId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUERY_KEY }),
    onError: () => setActionError(t("admin.users.errors.unblockFailed")),
  });

  async function handleFormSubmit(data: AdminUserCreate | AdminUserUpdate) {
    if (editingUser) {
      await updateMutation.mutateAsync({ id: editingUser.id, payload: data as AdminUserUpdate });
    } else {
      await createMutation.mutateAsync(data as AdminUserCreate);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2 text-sm">
          <Link to="/projects" className="text-primary hover:underline">{t("nav.backToProjects")}</Link>
          <span className="text-border">/</span>
          <h1 className="text-lg font-semibold m-0">{t("admin.users.title")}</h1>
        </div>
        <Button onClick={() => { setShowForm(true); setEditingUser(null); setActionError(null); }} size="sm">
          {t("admin.users.newUser")}
        </Button>
      </div>

      {actionError && (
        <p role="alert" className="text-sm text-destructive">{actionError}</p>
      )}

      {isLoading && <p>{t("admin.users.loading")}</p>}
      {isError && <p className="text-destructive">{t("admin.users.failed")}</p>}

      {data && (
        <Card>
          <CardContent className="p-0 overflow-hidden">
            <UserTable
              users={data.items}
              currentUserId={currentUser?.id}
              onEdit={(user) => { setEditingUser(user); setShowForm(false); setActionError(null); }}
              onBlock={(user) => { setActionError(null); blockMutation.mutate(user.id); }}
              onUnblock={(user) => { setActionError(null); unblockMutation.mutate(user.id); }}
            />
          </CardContent>
        </Card>
      )}

      {(showForm || editingUser) && (
        <UserForm
          user={editingUser ?? undefined}
          onSubmit={handleFormSubmit}
          onCancel={() => { setShowForm(false); setEditingUser(null); }}
        />
      )}
    </div>
  );
}
