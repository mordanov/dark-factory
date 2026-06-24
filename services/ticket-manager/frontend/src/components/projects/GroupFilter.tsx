import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { listGroups } from "../../api/groups";

interface GroupFilterProps {
  value: string | undefined;
  onChange: (groupId: string | undefined) => void;
}

export function GroupFilter({ value, onChange }: GroupFilterProps) {
  const { t } = useTranslation("common");
  const { data: groups = [] } = useQuery({
    queryKey: ["groups"],
    queryFn: listGroups,
  });

  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value || undefined)}
      className="border rounded px-2 py-1 text-sm"
      aria-label={t("groups.filter_label")}
    >
      <option value="">{t("groups.all_groups")}</option>
      {groups.map((g) => (
        <option key={g.id} value={g.id}>
          {g.identifier} — {g.name}
        </option>
      ))}
    </select>
  );
}
