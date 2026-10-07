import { describe, expect, it } from "vitest";
import { containsAnyFilter, literalPattern, quotePostgrestValue } from "./postgrest";

describe("literalPattern", () => {
  it("prefixes the ARE literal director, leaving the term untouched", () => {
    expect(literalPattern("R*D 100%_(a)")).toBe("***=R*D 100%_(a)");
  });
});

describe("quotePostgrestValue", () => {
  it("wraps in double quotes and escapes backslashes and quotes", () => {
    expect(quotePostgrestValue('a"b\\c')).toBe('"a\\"b\\\\c"');
  });
});

describe("containsAnyFilter", () => {
  // These strings were sent to the live PostgREST endpoint (2026-10-08) and matched the
  // same rows as ilike '%…%' (except "*", which ilike turns into a wildcard).
  it("keeps commas and parentheses inside the quoted value", () => {
    expect(containsAnyFilter(["title", "organization"], "창업, 벤처")).toBe(
      'title.imatch."***=창업, 벤처",organization.imatch."***=창업, 벤처"',
    );
    expect(containsAnyFilter(["title"], "기술개발(R&D)")).toBe('title.imatch."***=기술개발(R&D)"');
  });

  it("passes LIKE wildcards and '*' through as plain characters", () => {
    expect(containsAnyFilter(["title"], "100%_*")).toBe('title.imatch."***=100%_*"');
  });

  it("escapes a backslash for the quoted value", () => {
    expect(containsAnyFilter(["title"], "a\\b")).toBe('title.imatch."***=a\\\\b"');
  });
});
