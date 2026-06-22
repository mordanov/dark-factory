import { useTranslation } from "react-i18next";
import type { AdminUserResponse } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface UserTableProps {
  users: AdminUserResponse[];
  currentUserId?: string;
  onEdit: (user: AdminUserResponse) => void;
  onBlock: (user: AdminUserResponse) => void;
  onUnblock: (user: AdminUserResponse) => void;
}

export function UserTable({ users, currentUserId, onEdit, onBlock, onUnblock }: UserTableProps) {
  const { t } = useTranslation();

  if (users.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("admin.users.empty")}</p>;
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("admin.users.table.email")}</TableHead>
            <TableHead>{t("admin.users.table.role")}</TableHead>
            <TableHead>{t("admin.users.table.status")}</TableHead>
            <TableHead>{t("admin.users.table.actions")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {users.map((user) => {
            const isBlocked = user.blocked_at !== null;
            const isSelf = user.id === currentUserId;
            return (
              <TableRow key={user.id} className={isSelf ? "bg-muted/30" : ""}>
                <TableCell className="text-sm">{user.email}</TableCell>
                <TableCell>
                  <Badge variant={user.role === "administrator" ? "default" : "secondary"} className="text-xs">
                    {t(`admin.users.role.${user.role}`)}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge variant={isBlocked ? "destructive" : "outline"} className="text-xs">
                    {isBlocked ? t("admin.users.status.blocked") : t("admin.users.status.active")}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div className="flex gap-2 flex-wrap">
                    <Button variant="ghost" size="sm" onClick={() => onEdit(user)} disabled={isSelf}>
                      {t("admin.users.actions.edit")}
                    </Button>
                    {!isSelf && (
                      isBlocked ? (
                        <Button variant="ghost" size="sm" className="text-green-600 hover:text-green-700" onClick={() => onUnblock(user)}>
                          {t("admin.users.actions.unblock")}
                        </Button>
                      ) : (
                        <Button variant="ghost" size="sm" className="text-destructive hover:text-destructive" onClick={() => onBlock(user)}>
                          {t("admin.users.actions.block")}
                        </Button>
                      )
                    )}
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
