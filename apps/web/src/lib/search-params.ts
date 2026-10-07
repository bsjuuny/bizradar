/** Next.js page searchParams: a key repeated in the URL (?q=a&q=b) arrives as an array. */
export type SearchParams = Record<string, string | string[] | undefined>;

/** The first value of a search param, "" when absent. */
export function one(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

/** `value` if it is one of `allowed`, else undefined. */
export function enumValue<T extends string>(value: string, allowed: readonly T[]): T | undefined {
  return allowed.includes(value as T) ? (value as T) : undefined;
}
