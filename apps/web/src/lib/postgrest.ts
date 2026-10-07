/**
 * 검색어를 LIKE 패턴 안에 넣을 수 있게 바꾼다. %, _, \ 는 이스케이프한다. "*"는 PostgREST가
 * like/ilike 값에서 "%"의 별칭으로 바꿔 버리고 이스케이프할 방법이 없어서(2026-10-07 실측:
 * "R\*D"도 0건) 한 글자 와일드카드 "_"로 바꾼다 - "*" 자신을 포함해 그 자리의 아무 글자와
 * 맞고, 여러 글자를 건너뛰지는 않는다.
 */
export function escapeLikeTerm(term: string): string {
  return term.replace(/[\\%_]/g, "\\$&").replace(/\*/g, "_");
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
