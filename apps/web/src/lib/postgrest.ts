/** LIKE 패턴 안에서 와일드카드·이스케이프 문자로 읽히지 않도록 %, _, \ 를 이스케이프한다. */
export function escapeLikeTerm(term: string): string {
  return term.replace(/[\\%_]/g, "\\$&");
}

/**
 * PostgREST의 or=(...) 안에서는 , ( ) 가 구분자라서 값에 그대로 넣으면 "failed to parse
 * logic tree"로 요청 전체가 실패한다 - 검색어 "창업, 벤처"로 실측(2026-10-07). 값을 큰따옴표로
 * 감싸고 그 안의 \ 와 " 만 이스케이프한다.
 */
export function quotePostgrestValue(value: string): string {
  return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

/** columns 중 하나라도 term을 포함하는 행 - `.or()`에 넘기는 필터 문자열. */
export function ilikeAnyFilter(columns: readonly string[], term: string): string {
  const pattern = quotePostgrestValue(`%${escapeLikeTerm(term)}%`);
  return columns.map((column) => `${column}.ilike.${pattern}`).join(",");
}
