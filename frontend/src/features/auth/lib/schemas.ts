/**
 * Zod schemas mirroring the backend's Pydantic validation.
 *
 * The backend's Argon2id policy is min-12 (per design.md §D8 / ADR-008 §8c);
 * we reproduce that here so users get instant feedback rather than a 400.
 */
import { z } from "zod";

const passwordPolicy = z.string().min(12, "Password must be at least 12 characters");

export const loginSchema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(1, "Password required"),
});
export type LoginInput = z.infer<typeof loginSchema>;

export const registerSchema = z.object({
  email: z.string().email("Enter a valid email"),
  password: passwordPolicy,
});
export type RegisterInput = z.infer<typeof registerSchema>;

export const magicLinkRequestSchema = z.object({
  email: z.string().email("Enter a valid email"),
});
export type MagicLinkRequestInput = z.infer<typeof magicLinkRequestSchema>;

export const passwordResetRequestSchema = magicLinkRequestSchema;
export type PasswordResetRequestInput = z.infer<typeof passwordResetRequestSchema>;

export const passwordResetCompleteSchema = z.object({
  password: passwordPolicy,
});
export type PasswordResetCompleteInput = z.infer<typeof passwordResetCompleteSchema>;
