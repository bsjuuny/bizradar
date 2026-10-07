/**
 * Third-party URLs are data, not trusted markup. Only absolute HTTP(S) URLs are safe
 * to expose as clickable links; in particular, reject javascript: and data: payloads.
 */
export function safeExternalUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    if (url.username || url.password) return null;
    return url.toString();
  } catch {
    return null;
  }
}
