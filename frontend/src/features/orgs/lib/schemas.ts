/**
 * Zod schemas mirroring backend Pydantic + slug regex (tenants/slugs.py).
 *
 * Slug format must match `^[a-z0-9-]{3,63}$`; the reserved-word list is
 * enforced server-side only — clients shouldn't second-guess it.
 */
import { z } from "zod";

const slugSchema = z
  .string()
  .min(3, "Slug must be at least 3 characters")
  .max(63, "Slug must be at most 63 characters")
  .regex(/^[a-z0-9-]+$/, "Slug may contain lowercase letters, digits and hyphens only");

export const createOrgSchema = z.object({
  name: z.string().min(1, "Name required").max(120, "Name too long"),
  slug: slugSchema,
});
export type CreateOrgInput = z.infer<typeof createOrgSchema>;

// Operational roles only. Compliance roles (`compliance_officer`, `dpo`) are
// specialised — read-audit cross-org and GDPR scrub respectively. They get
// their own assignment surface (issue #32); not exposed in the Members invite UI.
export const inviteMemberSchema = z.object({
  email: z.string().email("Enter a valid email"),
  role: z.enum(["admin", "member", "viewer"]),
});
export type InviteMemberInput = z.infer<typeof inviteMemberSchema>;

export const createProjectSchema = z.object({
  name: z.string().min(1, "Name required").max(120, "Name too long"),
  slug: slugSchema,
  description: z.string().max(1000, "Description too long").optional(),
});
export type CreateProjectInput = z.infer<typeof createProjectSchema>;

export const shareProjectSchema = z.object({
  email: z.string().email("Enter a valid email"),
  ttl_days: z.number().int().min(1).max(30).optional(),
});
export type ShareProjectInput = z.infer<typeof shareProjectSchema>;
