-- Support Radar 목록 조회와 "모집 중"의 단 하나의 정의.
--
-- support_program_is_open(recruiting, application_end): 출처가 모집 중이라고 하거나(recruiting),
-- 모집 여부를 알 수 없을 때(null)는 마감일이 있으면, 그리고 마감일이 없거나 오늘(서울)
-- 이후일 때. 출처가 마감이라고 한 공고(false)는 날짜와 상관없이 마감이다.
-- application_end는 날짜의 자정(UTC, 수집기가 +00:00을 붙여 저장)이므로, 오늘(서울) 날짜도
-- 같은 방식으로 바꿔 비교한다(support_program_today_utc).
--
-- support_programs_listing: 모든 행 + is_open. 상세 화면과 워커의 중복 짝짓기
-- (worker/repositories/support_programs.py)가 읽는다.
--
-- list_support_programs(...): /support 목록. 필터·숨김·정렬·페이지를 한 SQL에서 처리한다.
--   1. filtered: 화면의 조건(모집 상태, IT, 투자연계, 출처, 지원분야, 검색어)을 모든 행에 적용.
--   2. visible: 기업마당 사본(duplicate_of가 있는 행)은 그 원본이 filtered 안에 있을 때만
--      뺀다 - "원본이 같은 결과에 함께 나온다"를 그대로 SQL로 쓴 것이라, 원본 쪽 값이 NULL이든
--      조건이 몇 개 더 생기든 공고가 사라질 수 없다. duplicate_of는 워커가 매시간 맞추는
--      짝일 뿐이고, 숨김은 매 조회 시점에 정해진다.
--   3. 모집 중인 공고가 먼저, 그 안에서는 마감이 가까운 순, 마감된 공고는 최근 마감 순.
--   검색어는 strpos(lower(...))로 찾는다 - LIKE 패턴이 아니라서 %, _, * 같은 글자도 그대로
--   글자로 찾는다.
--
-- security_invoker/security invoker: 조회하는 사용자의 RLS를 그대로 적용한다
-- (opportunities_current와 같은 방식).
-- 주의: 뷰의 p.* 는 만들 때의 컬럼 목록으로 고정된다. support_programs에 컬럼을 더하는
-- 마이그레이션은 이 뷰(와 이를 읽는 함수)도 다시 만들어야 그 컬럼을 읽을 수 있다.

create function support_program_today_utc()
  returns timestamptz
  language sql
  stable
  as $$
    select ((now() at time zone 'Asia/Seoul')::date)::timestamp at time zone 'UTC'
  $$;

create function support_program_is_open(recruiting boolean, application_end timestamptz)
  returns boolean
  language sql
  stable
  as $$
    select coalesce(recruiting, application_end is not null)
      and (application_end is null or application_end >= support_program_today_utc())
  $$;

create view support_programs_listing
  with (security_invoker = true)
  as
  select p.*, support_program_is_open(p.recruiting, p.application_end) as is_open
  from support_programs p;

grant select on support_programs_listing to authenticated;

create function list_support_programs(
  p_status text default 'open',
  p_it_only boolean default false,
  p_investment_only boolean default false,
  p_source text default null,
  p_categories text[] default null,
  p_term text default null,
  p_limit integer default 20,
  p_offset integer default 0
)
  returns json
  language sql
  stable
  security invoker
  as $$
    with filtered as (
      select l.*
      from support_programs_listing l
      where (p_status = 'all' or l.is_open)
        and (
          p_status <> 'closing'
          or (
            l.application_end >= support_program_today_utc()
            and l.application_end <= support_program_today_utc() + interval '7 days'
          )
        )
        and (not p_it_only or l.it_related)
        and (not p_investment_only or l.investment_linked)
        and (p_source is null or l.source = p_source)
        and (p_categories is null or l.category = any (p_categories))
        and (
          p_term is null
          or strpos(lower(l.title), lower(p_term)) > 0
          or strpos(lower(coalesce(l.organization, '')), lower(p_term)) > 0
        )
    ),
    visible as (
      select f.*
      from filtered f
      where f.duplicate_of is null
        or not exists (select 1 from filtered o where o.id = f.duplicate_of)
    ),
    page_rows as (
      select
        v.id, v.source, v.title, v.organization, v.supervising_type, v.category, v.region,
        v.recruiting, v.is_open, v.investment_linked, v.it_related, v.application_end,
        v.application_period_text
      from visible v
      order by
        v.is_open desc,
        case when v.is_open then v.application_end end asc nulls last,
        v.application_end desc nulls last,
        v.id
      limit p_limit
      offset p_offset
    )
    select json_build_object(
      'total', (select count(*) from visible),
      'items', coalesce(
        (
          select json_agg(
            row_to_json(r)
            order by
              r.is_open desc,
              case when r.is_open then r.application_end end asc nulls last,
              r.application_end desc nulls last,
              r.id
          )
          from page_rows r
        ),
        '[]'::json
      )
    )
  $$;

grant execute on function list_support_programs(
  text, boolean, boolean, text, text[], text, integer, integer
) to authenticated;
