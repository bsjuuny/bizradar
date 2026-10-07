-- Support Radar 목록 조회와 "모집 중"의 단 하나의 정의.
--
-- last_seen_at: 목록형 출처(기업마당)에서 그 공고를 마지막으로 본 시각. 기업마당 응답은 "지금
-- 게시 중인 공고 전부"라서, 워커가 매시간 응답에 있던 공고마다 이 값을 새로 쓴다
-- (worker/jobs/bizinfo_job.py). 날짜 없이 "예산 소진시까지"인 공고(65%)는 목록에서 내려가는
-- 것 말고는 마감될 길이 없는데, 내려간 공고를 마감 처리하는 단계는 응답이 완전할 때만
-- 돈다 - 키가 만료되거나 응답이 계속 불완전하면 그 단계가 멈추고, 그런 공고는 영원히 모집
-- 중으로 남는다. 그래서 3일 넘게 목록에서 보이지 않은 행은 모집 중으로 보지 않는다. 행마다
-- 따지므로 응답에 공고 하나가 빠지거나 겹쳐도 그 공고만 영향을 받는다. NULL은 "추적하지
-- 않음"(K-Startup, 그리고 이 컬럼이 생기기 전에 저장된 행)이고, 이 조건을 적용하지 않는다 -
-- 일부러 채워 넣지 않는다: 채워 두면 새 워커가 돌기 전에 3일이 지나는 순간 기업마당 공고가
-- 전부 사라진다.
--
-- is_open(support_programs): "모집 중"의 유일한 정의이자 PostgREST 계산 컬럼(select=...,is_open,
-- is_open=eq.true). 출처가 모집 중이라고 하거나(recruiting) 모집 여부를 모를 때(null)는 마감일이
-- 있으면, 그리고 마감일이 없거나 오늘(서울) 이후이고, 추적하는 행이라면 최근 3일 안에 목록에
-- 있었을 때. 출처가 마감이라고 한 공고(false)는 날짜와 상관없이 마감이다.
-- 상세 화면, 워커의 중복 짝짓기, list_support_programs가 모두 이 함수만 쓴다. 뷰(p.*)로 내보내면
-- 뷰를 만들 때의 컬럼 목록으로 고정돼 컬럼을 더할 때마다 다시 만들어야 해서, 계산 컬럼으로 둔다.
-- application_end는 날짜의 자정(UTC, 수집기가 +00:00을 붙여 저장)이므로, 오늘(서울) 날짜도
-- 같은 방식으로 바꿔 비교한다(support_program_today_utc).
--
-- list_support_programs(...): /support 목록. 필터·숨김·정렬·페이지를 한 함수에서 처리한다.
--   1. filtered: 화면의 조건(모집 상태, IT, 투자연계, 출처, 지원분야, 검색어)을 모든 행에 적용.
--      목록에 필요한 컬럼만 뽑는다(raw_payload·description은 끌고 다니지 않는다).
--   2. visible: 기업마당 사본(duplicate_of가 있는 행)은 그 원본이 filtered 안에 있을 때만
--      뺀다 - "원본이 같은 결과에 함께 나온다"를 그대로 SQL로 쓴 것이라, 원본 쪽 값이 NULL이든
--      조건이 몇 개 더 생기든 공고가 사라질 수 없다. duplicate_of는 워커가 매시간 맞추는
--      짝일 뿐이고, 숨김은 매 조회 시점에 정해진다.
--   3. ordered: 모집 중인 공고가 먼저, 그 안에서는 마감이 가까운 순, 마감된 공고는 최근 마감 순.
--      순서는 여기 한 번만 정하고(position), 페이지 자르기와 결과 배열 순서가 모두 그것을 쓴다.
--   검색어는 strpos(lower(...))로 찾는다 - LIKE 패턴이 아니라서 %, _, * 같은 글자도 그대로
--   글자로 찾는다. 잘못된 인자(모르는 상태값, 범위 밖 페이지 크기·offset·기간)는 오류로
--   거절한다 - RPC는 로그인한 사용자가 직접 부를 수 있어서 조용히 다른 결과를 내면 안 된다.
--
-- security invoker: 조회하는 사용자의 RLS를 그대로 적용한다.

alter table support_programs add column last_seen_at timestamptz;

create function support_program_today_utc()
  returns timestamptz
  language sql
  stable
  as $$
    select ((now() at time zone 'Asia/Seoul')::date)::timestamp at time zone 'UTC'
  $$;

create function is_open(p support_programs)
  returns boolean
  language sql
  stable
  as $$
    select coalesce(p.recruiting, p.application_end is not null)
      and (p.application_end is null or p.application_end >= support_program_today_utc())
      and (p.last_seen_at is null or p.last_seen_at >= now() - interval '3 days')
  $$;

create function list_support_programs(
  p_status text default 'open',
  p_it_only boolean default false,
  p_investment_only boolean default false,
  p_source text default null,
  p_categories text[] default null,
  p_term text default null,
  p_closing_days integer default 7,
  p_limit integer default 20,
  p_offset integer default 0
)
  returns jsonb
  language plpgsql
  stable
  security invoker
  as $$
  begin
    if p_status is null or p_status not in ('open', 'closing', 'all') then
      raise exception 'list_support_programs: unknown status %', p_status
        using errcode = '22023';
    end if;
    if p_limit is null or p_limit < 1 or p_limit > 100
      or p_offset is null or p_offset < 0
      or p_closing_days is null or p_closing_days < 0 or p_closing_days > 366 then
      raise exception 'list_support_programs: invalid paging or window'
        using errcode = '22023';
    end if;

    return (
      with candidates as (
        select
          p.id, p.duplicate_of, p.source, p.title, p.organization, p.supervising_type,
          p.category, p.region, p.recruiting, p.investment_linked, p.it_related,
          p.application_end, p.application_period_text,
          is_open(p) as is_open
        from support_programs p
        where (not p_it_only or p.it_related)
          and (not p_investment_only or p.investment_linked)
          and (p_source is null or p.source = p_source)
          and (p_categories is null or p.category = any (p_categories))
          and (
            p_term is null
            or strpos(lower(p.title), lower(p_term)) > 0
            or strpos(lower(coalesce(p.organization, '')), lower(p_term)) > 0
          )
      ),
      filtered as (
        select c.*
        from candidates c
        where (p_status = 'all' or c.is_open)
          and (
            p_status <> 'closing'
            or (
              c.application_end >= support_program_today_utc()
              and c.application_end
                <= support_program_today_utc() + make_interval(days => p_closing_days)
            )
          )
      ),
      visible as (
        select f.*
        from filtered f
        where f.duplicate_of is null
          or not exists (select 1 from filtered o where o.id = f.duplicate_of)
      ),
      ordered as (
        select
          v.*,
          row_number() over (
            order by
              v.is_open desc,
              case when v.is_open then v.application_end end asc nulls last,
              v.application_end desc nulls last,
              v.id
          ) as position
        from visible v
      ),
      page_rows as (
        select
          o.id, o.source, o.title, o.organization, o.supervising_type, o.category, o.region,
          o.recruiting, o.is_open, o.investment_linked, o.it_related, o.application_end,
          o.application_period_text, o.position
        from ordered o
        where o.position > p_offset
          and o.position <= p_offset::bigint + p_limit
      )
      select jsonb_build_object(
        'total', (select count(*) from visible),
        'items', coalesce(
          (select jsonb_agg(to_jsonb(r) - 'position' order by r.position) from page_rows r),
          '[]'::jsonb
        )
      )
    );
  end;
  $$;

grant execute on function list_support_programs(
  text, boolean, boolean, text, text[], text, integer, integer, integer
) to authenticated;
