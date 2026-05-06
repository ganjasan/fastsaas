/**
 * Renderer for SearchHits with `entity_type === "member"`. Foundation
 * provider. Title is the actor's display name; subtitle is the email.
 */
import { User } from "lucide-react";
import type { ReactNode } from "react";

import type { RendererProps } from "../registries/rendererRegistry";

export function MemberRenderer({ hit }: RendererProps): ReactNode {
  return (
    <>
      <User className="h-4 w-4 shrink-0 text-muted-foreground" />
      <div className="flex min-w-0 flex-col">
        <span className="truncate text-sm">{hit.title}</span>
        {hit.subtitle ? (
          <span className="truncate text-xs text-muted-foreground">{hit.subtitle}</span>
        ) : null}
      </div>
    </>
  );
}
