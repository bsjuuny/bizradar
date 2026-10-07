/**
 * 검색어를 글자 그대로 찾는 정규식 - imatch(~*, 대소문자 무시)에 넘긴다. "***=" 접두어는
 * Postgres 정규식(ARE)에서 "나머지를 전부 글자 그대로 읽으라"는 뜻이라 %, _, *, (, ) 같은 글자도
 * 그냥 글자다. ilike로는 안 된다: PostgREST가 like/ilike 값의 "*"를 "%"로 바꾸고 그걸 막을
 * 방법이 없다("R\*D"도 0건, 2026-10-07 실측). imatch 값은 건드리지 않는다 - 2026-10-08 실측:
 * AI, 데이터, (주), R&D, 100%, "창업, 벤처"는 ilike '%…%'와 같은 건수, "a*b"는 ilike 190건
 * (와일드카드로 읽힘) 대 0건. 그래서 Watch 미리보기와 matchesWatch(글자 그대로 포함 여부)가
 * 같은 결과를 낸다. pg_trgm GIN 인덱스는 정규식 검색에도 쓰인다.
 */
export function literalPattern(term: string): string {
  return `***=${term}`;
}

/**
 * PostgREST의 or=(...) 안에서는 , ( ) 가 구분자라서 값에 그대로 넣으면 "failed to parse
 * logic tree"로 요청 전체가 실패한다 - 검색어 "창업, 벤처"로 실측(2026-10-07). 값을 큰따옴표로
 * 감싸고 그 안의 \ 와 " 만 이스케이프한다.
 */
export function quotePostgrestValue(value: string): string {
  return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

/** columns 중 하나라도 term을 글자 그대로 포함하는 행 - `.or()`에 넘기는 필터 문자열. */
export function containsAnyFilter(columns: readonly string[], term: string): string {
  const pattern = quotePostgrestValue(literalPattern(term));
  return columns.map((column) => `${column}.imatch.${pattern}`).join(",");
}
