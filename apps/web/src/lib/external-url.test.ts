import { describe, expect, it } from "vitest";
import { safeExternalUrl } from "./external-url";

describe("safeExternalUrl", () => {
  it("accepts absolute HTTP and HTTPS URLs", () => {
    expect(safeExternalUrl("https://example.com/path?q=1")).toBe(
      "https://example.com/path?q=1",
    );
    expect(safeExternalUrl("http://example.com")).toBe("http://example.com/");
  });

  it("rejects executable, relative, malformed, and credential-bearing URLs", () => {
    expect(safeExternalUrl("javascript:alert(1)")).toBeNull();
    expect(safeExternalUrl("data:text/html,<script>alert(1)</script>")).toBeNull();
    expect(safeExternalUrl("/relative/path")).toBeNull();
    expect(safeExternalUrl("https://user:password@example.com/path")).toBeNull();
    expect(safeExternalUrl("not a url")).toBeNull();
    expect(safeExternalUrl(null)).toBeNull();
  });
});
