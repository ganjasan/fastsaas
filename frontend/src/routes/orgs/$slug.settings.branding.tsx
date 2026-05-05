/**
 * /orgs/$slug/settings/branding — admin-only Phase 1 theme picker (ADR-012).
 *
 * Admins pick from one of five pre-defined presets and an optional
 * `mode_default` for new users. Saves via `PATCH /orgs/{slug}/theme`. The
 * picker live-previews on hover; persisted choice propagates after Save.
 */
import { createFileRoute, useParams } from "@tanstack/react-router";

import { useGetOrgOrgsSlugGet } from "@/api/generated/orgs/orgs";
import { Skeleton } from "@/components/ui/skeleton";
import { ThemePicker } from "@/features/theme/ThemePicker";
import { parseOrgTheme } from "@/lib/theme";

export const Route = createFileRoute("/orgs/$slug/settings/branding")({
  component: BrandingPage,
});

function BrandingPage() {
  const { slug } = useParams({ from: "/orgs/$slug/settings/branding" });
  const { data, isLoading } = useGetOrgOrgsSlugGet(slug);

  if (isLoading || !data) {
    return (
      <div className="space-y-6">
        <header>
          <h2 className="text-xl font-semibold tracking-tight">Branding</h2>
          <p className="text-sm text-muted-foreground">Loading…</p>
        </header>
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  const theme = parseOrgTheme(data.theme ?? {});

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-xl font-semibold tracking-tight">Branding</h2>
        <p className="text-sm text-muted-foreground">
          Pick a theme preset for the organisation. Phase 1 — five curated presets; a full editor
          lands in a follow-up.
        </p>
      </header>
      <ThemePicker slug={slug} currentPreset={theme.preset} currentMode={theme.mode_default} />
    </div>
  );
}
