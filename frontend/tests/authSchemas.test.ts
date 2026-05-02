import { describe, expect, test } from "vitest";

import {
  loginSchema,
  passwordResetCompleteSchema,
  registerSchema,
} from "@/features/auth/lib/schemas";

describe("loginSchema", () => {
  test("accepts a valid email + password pair", () => {
    // GIVEN a valid login payload
    const result = loginSchema.safeParse({ email: "user@example.com", password: "anything" });
    // THEN it parses
    expect(result.success).toBe(true);
  });

  test("rejects malformed email", () => {
    // GIVEN an email without @
    const result = loginSchema.safeParse({ email: "no-at-sign", password: "anything" });
    // THEN it fails on the email field
    expect(result.success).toBe(false);
    if (!result.success) {
      const first = result.error.issues[0];
      expect(first?.path).toEqual(["email"]);
    }
  });
});

describe("registerSchema", () => {
  test("accepts a 12-char password", () => {
    // GIVEN a 12-char password (the minimum)
    const result = registerSchema.safeParse({
      email: "user@example.com",
      password: "exactly12chr",
    });
    // THEN it parses
    expect(result.success).toBe(true);
  });

  test("rejects an 11-char password with the policy message", () => {
    // GIVEN an 11-char password
    const result = registerSchema.safeParse({
      email: "user@example.com",
      password: "elevenchars",
    });
    // THEN it fails with the password-policy message
    expect(result.success).toBe(false);
    if (!result.success) {
      const passwordIssue = result.error.issues.find((i) => i.path[0] === "password");
      expect(passwordIssue?.message).toMatch(/12 characters/i);
    }
  });
});

describe("passwordResetCompleteSchema", () => {
  test("rejects a short password the same way registerSchema does", () => {
    // GIVEN a too-short reset password
    const result = passwordResetCompleteSchema.safeParse({ password: "tooshort" });
    // THEN the same min-12 message surfaces
    expect(result.success).toBe(false);
    if (!result.success) {
      const first = result.error.issues[0];
      expect(first?.message).toMatch(/12 characters/i);
    }
  });
});
