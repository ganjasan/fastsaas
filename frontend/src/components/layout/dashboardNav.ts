/**
 * `useDashboardSections(slug)` — context-aware sidebar nav.
 *
 * Workspace context (URL not under a specific project): shows the org-level
 * nav — Overview / Projects / Settings.
 *
 * Project context (URL under `/orgs/{slug}/projects/{projectSlug}/...`):
 * replaces the workspace nav with project-scoped items + a "← Back to
 * projects" header that exits back to the workspace's project list.
 *
 * Render-style aesthetic: each context owns its own sidebar; switching
 * contexts swaps the entire nav rather than nesting.
 */
import { useRouterState } from "@tanstack/react-router";
import { ArrowLeft, FolderKanban, LayoutDashboard, Settings, Share2 } from "lucide-react";

import type { NavSection } from "@/components/layout/Shell";

const PROJECT_PATH_RE = /^\/orgs\/([^/]+)\/projects\/([^/]+)(?:\/|$)/;

export function useDashboardSections(workspaceSlug: string): NavSection[] {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const projectMatch = pathname.match(PROJECT_PATH_RE);
  if (projectMatch?.[1] && projectMatch[2]) {
    return projectSections(projectMatch[1], projectMatch[2]);
  }
  return workspaceSections(workspaceSlug);
}

function workspaceSections(slug: string): NavSection[] {
  // FastSaaS workspace dashboard ships three items today; future domain
  // features extend this list. No section labels at this size — Render
  // aesthetic shows them only when there are multiple groups.
  return [
    {
      items: [
        {
          to: `/orgs/${slug}`,
          label: "Overview",
          icon: LayoutDashboard,
          exact: true,
        },
        { to: `/orgs/${slug}/projects`, label: "Projects", icon: FolderKanban },
        { to: `/orgs/${slug}/settings/members`, label: "Settings", icon: Settings },
      ],
    },
  ];
}

function projectSections(slug: string, projectSlug: string): NavSection[] {
  return [
    {
      // Back-to-workspace anchor at the top of the project sidebar.
      items: [
        {
          to: `/orgs/${slug}/projects`,
          label: "Back to projects",
          icon: ArrowLeft,
        },
      ],
    },
    {
      label: projectSlug.toUpperCase(),
      items: [
        {
          to: `/orgs/${slug}/projects/${projectSlug}`,
          label: "Overview",
          icon: LayoutDashboard,
          exact: true,
        },
        {
          to: `/orgs/${slug}/projects/${projectSlug}/sharing`,
          label: "Sharing",
          icon: Share2,
        },
      ],
    },
  ];
}
