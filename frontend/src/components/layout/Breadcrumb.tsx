/**
 * Breadcrumb — single-segment for v1, derived from the URL via TanStack
 * Router state. Renders the current section name (Overview / Projects /
 * Settings / Members / Branding / project slug fallback).
 *
 * Multi-segment breadcrumbs (e.g. `Projects / <project name>`) require a
 * data fetch to resolve display names; deferred to a follow-up.
 */
import { useRouterState } from "@tanstack/react-router";

const SECTION_FROM_PATH: Array<[RegExp, string]> = [
  [/\/admin\/orgs\/?$/, "Orgs"],
  [/\/admin\/metrics\/?$/, "Metrics"],
  [/\/admin\/health\/?$/, "Health"],
  [/\/admin\/design-system\/?$/, "Design system"],
  [/\/admin\/auth\/?$/, "Auth"],
  [/\/admin\/oauth\/?$/, "OAuth providers"],
  [/\/admin\/?$/, "Admin"],
  [/\/orgs\/[^/]+\/settings\/members$/, "Members"],
  [/\/orgs\/[^/]+\/settings\/branding$/, "Branding"],
  [/\/orgs\/[^/]+\/settings$/, "Settings"],
  [/\/orgs\/[^/]+\/projects\/[^/]+$/, "Project"],
  [/\/orgs\/[^/]+\/projects$/, "Projects"],
  [/\/orgs\/[^/]+\/?$/, "Overview"],
];

export function Breadcrumb() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const label = SECTION_FROM_PATH.find(([re]) => re.test(pathname))?.[1] ?? "";

  if (label.length === 0) return null;
  return (
    <nav aria-label="Breadcrumb" className="text-sm font-medium text-foreground">
      {label}
    </nav>
  );
}
