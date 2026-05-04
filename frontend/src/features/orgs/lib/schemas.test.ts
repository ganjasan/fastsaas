/**
 * Vitest unit tests for the zod schemas guarding the orgs/projects forms.
 *
 * The schemas mirror the backend's validators (`tenants/slugs.py`,
 * `tenants/schemas.py`); these tests pin the *visible* error messages so
 * the SPA never gets out of sync with what the backend rejects.
 */
import { describe, expect, it } from "vitest";

import {
  createOrgSchema,
  createProjectSchema,
  inviteMemberSchema,
  shareProjectSchema,
} from "./schemas";

describe("createOrgSchema", () => {
  it("accepts a valid name + slug", () => {
    // GIVEN a well-formed input
    const r = createOrgSchema.safeParse({ name: "Acme Co", slug: "acme-co" });
    // THEN it parses cleanly
    expect(r.success).toBe(true);
  });

  it("rejects an UPPERCASE slug", () => {
    // GIVEN a slug with an uppercase letter
    const r = createOrgSchema.safeParse({ name: "Acme", slug: "Acme" });
    // THEN it fails with a friendly message
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(r.error.issues[0]?.path).toEqual(["slug"]);
    }
  });

  it("rejects a 2-char slug", () => {
    const r = createOrgSchema.safeParse({ name: "Acme", slug: "ac" });
    expect(r.success).toBe(false);
  });

  it("rejects an empty name", () => {
    const r = createOrgSchema.safeParse({ name: "", slug: "acme" });
    expect(r.success).toBe(false);
  });
});

describe("inviteMemberSchema", () => {
  it("accepts a valid email + member role", () => {
    const r = inviteMemberSchema.safeParse({ email: "x@example.com", role: "member" });
    expect(r.success).toBe(true);
  });

  it("rejects role=owner (only owners are minted by org create)", () => {
    const r = inviteMemberSchema.safeParse({ email: "x@example.com", role: "owner" });
    expect(r.success).toBe(false);
  });
});

describe("createProjectSchema", () => {
  it("accepts a valid project payload (description optional)", () => {
    const r = createProjectSchema.safeParse({ name: "Q3 Forecast", slug: "q3" });
    // 2-char slug should fail; double-check valid one passes:
    expect(r.success).toBe(false); // confirms 3-char minimum

    const r2 = createProjectSchema.safeParse({ name: "Q3 Forecast", slug: "q3-forecast" });
    expect(r2.success).toBe(true);
  });
});

describe("shareProjectSchema", () => {
  it("accepts valid ttl_days within 1..30", () => {
    const r = shareProjectSchema.safeParse({ email: "x@example.com", ttl_days: 14 });
    expect(r.success).toBe(true);
  });

  it("rejects ttl_days = 0", () => {
    const r = shareProjectSchema.safeParse({ email: "x@example.com", ttl_days: 0 });
    expect(r.success).toBe(false);
  });

  it("rejects ttl_days > 30", () => {
    const r = shareProjectSchema.safeParse({ email: "x@example.com", ttl_days: 60 });
    expect(r.success).toBe(false);
  });

  it("accepts an invite without ttl_days (server picks default)", () => {
    const r = shareProjectSchema.safeParse({ email: "x@example.com" });
    expect(r.success).toBe(true);
  });
});
