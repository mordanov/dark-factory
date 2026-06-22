import { useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { searchTags } from "@/api/tickets";
import type { TagResponse } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

interface TagInputProps {
  value: string[];
  onChange: (tags: string[]) => void;
  disabled?: boolean;
}

export function TagInput({ value, onChange, disabled }: TagInputProps) {
  const { t } = useTranslation();
  const [input, setInput] = useState("");
  const [suggestions, setSuggestions] = useState<TagResponse[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (input.length < 1) { setSuggestions([]); setShowDropdown(false); return; }
    const timer = setTimeout(async () => {
      try {
        const results = await searchTags(input);
        setSuggestions(results.filter((tg) => !value.includes(tg.name)));
        setShowDropdown(true);
      } catch { /* ignore */ }
    }, 200);
    return () => clearTimeout(timer);
  }, [input, value]);

  function addTag(name: string) {
    const trimmed = name.trim();
    if (!trimmed || value.includes(trimmed) || value.length >= 10) return;
    onChange([...value, trimmed]);
    setInput("");
    setSuggestions([]);
    setShowDropdown(false);
    inputRef.current?.focus();
  }

  function removeTag(name: string) {
    onChange(value.filter((tg) => tg !== name));
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") { e.preventDefault(); if (input.trim()) addTag(input); }
    else if (e.key === "Escape") setShowDropdown(false);
  }

  return (
    <div>
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {value.map((tag) => (
            <Badge key={tag} variant="secondary" className="gap-1">
              {tag}
              {!disabled && (
                <button
                  type="button"
                  onClick={() => removeTag(tag)}
                  className="ml-0.5 rounded-full hover:bg-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  title={t("tickets.tagInput.remove", { tag })}
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </Badge>
          ))}
        </div>
      )}

      {!disabled && value.length < 10 && (
        <div className="relative">
          <Input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={() => setTimeout(() => setShowDropdown(false), 150)}
            placeholder={t("tickets.tagInput.placeholder")}
            className="h-8 text-sm"
          />
          {showDropdown && suggestions.length > 0 && (
            <ul className="absolute top-full left-0 right-0 bg-popover border border-border rounded shadow-md list-none m-0 p-0 z-50 max-h-48 overflow-y-auto">
              {suggestions.map((tg) => (
                <li
                  key={tg.id}
                  onMouseDown={() => addTag(tg.name)}
                  className="px-3 py-2 cursor-pointer text-sm hover:bg-accent hover:text-accent-foreground"
                >
                  {tg.name}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {value.length >= 10 && (
        <span className="text-xs text-muted-foreground">{t("tickets.tagInput.maxReached")}</span>
      )}
    </div>
  );
}
