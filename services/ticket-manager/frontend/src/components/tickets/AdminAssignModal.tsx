import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { listUsers } from "@/api/users";
import { assignUser } from "@/api/tickets";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface AdminAssignModalProps {
  open: boolean;
  onClose: () => void;
  ticketId: string;
  existingAssigneeIds: string[];
  onAssigned: () => void;
}

export function AdminAssignModal({
  open,
  onClose,
  ticketId,
  existingAssigneeIds,
  onAssigned,
}: AdminAssignModalProps) {
  const { t } = useTranslation();
  const [selectedUserId, setSelectedUserId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: users, isLoading: usersLoading } = useQuery({
    queryKey: ["users"],
    queryFn: listUsers,
    enabled: open,
  });

  const available = (users ?? []).filter((u) => !existingAssigneeIds.includes(u.id));

  function handleOpenChange(isOpen: boolean) {
    if (!isOpen) {
      setSelectedUserId("");
      setError(null);
      onClose();
    }
  }

  async function handleAssign() {
    if (!selectedUserId) return;
    setError(null);
    setLoading(true);
    try {
      await assignUser(ticketId, selectedUserId);
      setSelectedUserId("");
      onClose();
      onAssigned();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e.response?.data?.detail ?? t("tickets.assign.userFailed"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="w-full max-w-[95vw] sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("tickets.assign.assignTitle")}</DialogTitle>
          <DialogDescription>{t("tickets.assign.selectUser")}</DialogDescription>
        </DialogHeader>

        <div className="py-2">
          {usersLoading ? (
            <p className="text-sm text-muted-foreground">{t("tickets.assign.loadingUsers")}</p>
          ) : available.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("tickets.assign.allAssigned")}</p>
          ) : (
            <Select value={selectedUserId} onValueChange={setSelectedUserId}>
              <SelectTrigger>
                <SelectValue placeholder={t("tickets.assign.selectUser")} />
              </SelectTrigger>
              <SelectContent>
                {available.map((u) => (
                  <SelectItem key={u.id} value={u.id}>
                    {u.email} ({u.role})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          {error && <p role="alert" className="text-sm text-destructive mt-2">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={loading}>
            {t("tickets.assign.cancel")}
          </Button>
          <Button onClick={handleAssign} disabled={!selectedUserId || loading}>
            {loading ? t("common.loading") : t("tickets.assign.assign")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
