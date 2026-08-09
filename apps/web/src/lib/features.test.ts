import { describe, expect, it, vi } from "vitest";
import { isPlatformAdmin } from "./features";

describe("isPlatformAdmin", () => {
  it("returns false when ADMIN_EMAILS is unset", () => {
    vi.stubEnv("ADMIN_EMAILS", "");
    expect(isPlatformAdmin("someone@example.com")).toBe(false);
  });

  it("returns true for an exact match in the comma-separated allowlist", () => {
    vi.stubEnv("ADMIN_EMAILS", "a@example.com, b@example.com");
    expect(isPlatformAdmin("b@example.com")).toBe(true);
  });

  it("is case-insensitive", () => {
    vi.stubEnv("ADMIN_EMAILS", "Admin@Example.com");
    expect(isPlatformAdmin("admin@example.com")).toBe(true);
  });

  it("returns false for a non-matching email", () => {
    vi.stubEnv("ADMIN_EMAILS", "admin@example.com");
    expect(isPlatformAdmin("nobody@example.com")).toBe(false);
  });

  it("returns false for a null/undefined email", () => {
    vi.stubEnv("ADMIN_EMAILS", "admin@example.com");
    expect(isPlatformAdmin(null)).toBe(false);
    expect(isPlatformAdmin(undefined)).toBe(false);
  });
});
