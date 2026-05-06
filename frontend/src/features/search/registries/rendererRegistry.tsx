/**
 * Renderer registry — maps a SearchHit's `entity_type` to a React
 * component that renders one row inside the palette. The default
 * fallback renders title + subtitle, so a backend that ships a new
 * provider without a matching frontend renderer degrades gracefully.
 *
 * Mirrors the backend's `register_provider` pattern. Call
 * `registerRenderer` once at module-load (e.g. from a feature's
 * `index.ts`); duplicate keys throw — same fail-loud contract as the
 * backend registry.
 */
import type { ComponentType, ReactNode } from "react";

import type { SearchHit } from "../types";

export interface RendererProps {
  hit: SearchHit;
}

export type HitRenderer = ComponentType<RendererProps>;

const _renderers: Map<string, HitRenderer> = new Map();

export function registerRenderer(entityType: string, renderer: HitRenderer): void {
  if (_renderers.has(entityType)) {
    throw new Error(`SearchHit renderer for entity_type "${entityType}" already registered`);
  }
  _renderers.set(entityType, renderer);
}

export function getRenderer(entityType: string): HitRenderer | undefined {
  return _renderers.get(entityType);
}

export function renderHit(hit: SearchHit): ReactNode {
  const Renderer = _renderers.get(hit.entity_type);
  if (!Renderer) {
    if (typeof console !== "undefined") {
      console.warn(
        `[search] no renderer registered for entity_type "${hit.entity_type}" — using fallback`,
      );
    }
    return <FallbackRenderer hit={hit} />;
  }
  return <Renderer hit={hit} />;
}

function FallbackRenderer({ hit }: RendererProps): ReactNode {
  return (
    <div className="flex min-w-0 flex-col">
      <span className="truncate text-sm">{hit.title}</span>
      {hit.subtitle ? (
        <span className="truncate text-xs text-muted-foreground">{hit.subtitle}</span>
      ) : null}
    </div>
  );
}
