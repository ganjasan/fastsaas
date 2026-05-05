/**
 * ThemePicker — preset radio cards + mode_default selector + Save/Cancel.
 *
 * Hover/focus on a card calls `setPreviewPreset(p)` so the surrounding
 * dashboard re-themes live; mouse leave / blur reverts the preview.
 * Save persists via `PATCH /orgs/{slug}/theme` and invalidates the org
 * query so other components re-render with the new value.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";

import type { OrgThemeUpdateRequest } from "@/api/generated/fastSaaS.schemas";
import {
  getGetOrgOrgsSlugGetQueryKey,
  updateOrgThemeOrgsSlugThemePatch,
} from "@/api/generated/orgs/orgs";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useThemeContext } from "@/features/theme/ThemeProvider";
import { PRESETS, PRESET_LABELS, ThemeModeDefault, type ThemePreset } from "@/lib/theme";
import { cn } from "@/lib/utils/cn";

interface ThemePickerProps {
  slug: string;
  currentPreset: ThemePreset;
  currentMode: ThemeModeDefault | undefined;
}

const PRESET_ORDER: ThemePreset[] = ["default", "modern", "corporate", "dark", "high-contrast"];

export function ThemePicker({ slug, currentPreset, currentMode }: ThemePickerProps) {
  const { setPreviewPreset } = useThemeContext();
  const queryClient = useQueryClient();

  const [pendingPreset, setPendingPreset] = useState<ThemePreset>(currentPreset);
  const [pendingMode, setPendingMode] = useState<ThemeModeDefault | undefined>(currentMode);

  // Reset when the persisted props change (e.g. after a successful save).
  useEffect(() => setPendingPreset(currentPreset), [currentPreset]);
  useEffect(() => setPendingMode(currentMode), [currentMode]);

  const dirty = pendingPreset !== currentPreset || pendingMode !== currentMode;

  const save = useMutation({
    mutationFn: (body: OrgThemeUpdateRequest) => updateOrgThemeOrgsSlugThemePatch(slug, body),
    onSuccess: async () => {
      setPreviewPreset(null);
      await queryClient.invalidateQueries({
        queryKey: getGetOrgOrgsSlugGetQueryKey(slug),
      });
    },
  });

  const onSave = useCallback(async () => {
    await save.mutateAsync({
      preset: pendingPreset,
      mode_default: pendingMode ?? null,
    });
  }, [save, pendingPreset, pendingMode]);

  const onCancel = useCallback(() => {
    setPendingPreset(currentPreset);
    setPendingMode(currentMode);
    setPreviewPreset(null);
  }, [currentPreset, currentMode, setPreviewPreset]);

  // Apply preview when the user has selected a different preset.
  useEffect(() => {
    if (pendingPreset !== currentPreset) {
      setPreviewPreset(pendingPreset);
    } else {
      setPreviewPreset(null);
    }
    return () => setPreviewPreset(null);
  }, [pendingPreset, currentPreset, setPreviewPreset]);

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <Label>Preset</Label>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {PRESET_ORDER.map((preset) => {
            const lightVars = PRESETS[preset].light;
            const isPending = pendingPreset === preset;
            return (
              <button
                key={preset}
                type="button"
                onClick={() => setPendingPreset(preset)}
                onMouseEnter={() => setPreviewPreset(preset)}
                onMouseLeave={() =>
                  setPreviewPreset(pendingPreset !== currentPreset ? pendingPreset : null)
                }
                onFocus={() => setPreviewPreset(preset)}
                onBlur={() =>
                  setPreviewPreset(pendingPreset !== currentPreset ? pendingPreset : null)
                }
                className={cn(
                  "rounded-md border p-1 text-left transition-shadow",
                  isPending
                    ? "border-primary ring-2 ring-primary/40"
                    : "border-border hover:border-primary/60",
                )}
                aria-pressed={isPending}
              >
                <Card className="overflow-hidden">
                  <div
                    className="h-12 w-full"
                    style={{ background: `hsl(${lightVars.primary})` }}
                  />
                  <CardContent className="space-y-1 p-3">
                    <p className="text-sm font-medium">{PRESET_LABELS[preset]}</p>
                    <div className="flex gap-1">
                      {(["background", "secondary", "accent", "border"] as const).map((k) => (
                        <span
                          key={k}
                          className="h-3 w-3 rounded-full border border-border/50"
                          style={{ background: `hsl(${lightVars[k]})` }}
                        />
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </button>
            );
          })}
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="mode-default">Default mode for new users</Label>
        <Select
          value={pendingMode ?? ThemeModeDefault.system}
          onValueChange={(v) => setPendingMode(v as ThemeModeDefault)}
        >
          <SelectTrigger id="mode-default" className="w-60">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ThemeModeDefault.system}>System</SelectItem>
            <SelectItem value={ThemeModeDefault.light}>Light</SelectItem>
            <SelectItem value={ThemeModeDefault.dark}>Dark</SelectItem>
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          Each user can override this from the topbar.
        </p>
      </div>

      <div className="flex items-center gap-2">
        <Button onClick={onSave} disabled={!dirty || save.isPending}>
          {save.isPending ? "Saving…" : "Save"}
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={!dirty || save.isPending}>
          Cancel
        </Button>
        {save.isError && (
          <span className="text-sm text-destructive">Failed to save. Try again.</span>
        )}
      </div>
    </div>
  );
}
