import { describe, expect, it } from "vitest";
import { escapeLikeTerm, ilikeAnyFilter, quotePostgrestValue } from "./postgrest";

describe("escapeLikeTerm", () => {
  it("escapes LIKE wildcards and the escape character itself", () => {
    expect(escapeLikeTerm("100%_a\\b")).toBe("100\\%\\_a\\\\b");
  });

  it("turns '*' (PostgREST's alias for '%') into a single-character wildcard", () => {
    expect(escapeLikeTerm("R*D")).toBe("R_D");
  });
});

describe("quotePostgrestValue", () => {
  it("wraps in double quotes and escapes backslashes and quotes", () => {
    expect(quotePostgrestValue('a"b\\c')).toBe('"a\\"b\\\\c"');
  });
});

describe("ilikeAnyFilter", () => {
  // These strings were sent to the live PostgREST endpoint (2026-10-07) and matched the
  // same rows as a plain single-column ilike; unquoted, "창업, 벤처" failed to parse.
  it("keeps commas and parentheses inside the quoted value", () => {
    expect(ilikeAnyFilter(["title", "organization"], "창업, 벤처")).toBe(
      'title.ilike."%창업, 벤처%",organization.ilike."%창업, 벤처%"',
    );
    expect(ilikeAnyFilter(["title"], "기술개발(R&D)")).toBe('title.ilike."%기술개발(R&D)%"');
  });

  it("escapes LIKE wildcards before quoting", () => {
    expect(ilikeAnyFilter(["title"], "100%")).toBe('title.ilike."%100\\\\%%"');
  });
});
