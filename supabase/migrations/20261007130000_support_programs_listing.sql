-- Support Radar 목록 조회와 "모집 중"의 단 하나의 정의.
--
-- support_source_sync: 출처별로 "목록에서 내려간 공고를 마감 처리하는 단계"가 마지막으로 실제로
-- 돈 시각. 기업마당 공고의 65%는 신청기간이 "예산 소진시까지" 같은 문장이라 날짜로는 마감되지
-- 않고, 오직 그 단계(worker/jobs/bizinfo_job.py, 응답이 완전할 때만 돈다)로 마감된다. 키가
-- 만료되거나 응답이 계속 불완전하면 그 단계가 멈추고, 그런 공고는 영원히 모집 중으로 남는다 -
-- 그래서 마감 처리가 3일 넘게 돌지 않았으면 날짜 없는 기업마당 공고를 모집 중으로 보지 않는다.
--
-- is_open(support_programs): "모집 중"의 유일한 정의이자 PostgREST 계산 컬럼(select=...,is_open,
-- is_open=eq.true). 출처가 모집 중이라고 하거나(recruiting) 모집 여부를 모를 때(null)는 마감일이
-- 있으면, 그리고 마감일이 없거나 오늘(서울) 이후이고, 날짜 없는 기업마당 공고라면 위 마감 처리가
-- 최근에 돌았을 때. 출처가 마감이라고 한 공고(false)는 날짜와 상관없이 마감이다.
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

create table support_source_sync (
  source text primary key,
  last_complete_at timestamptz not null
);

alter table support_source_sync enable row level security;

-- Not sensitive, and is_open() reads it as the querying user.
create policy support_source_sync_select_authenticated on support_source_sync
  for select
  to authenticated
  using (true);

grant select on support_source_sync to authenticated;

-- The 2026-10-07 runs before this migration were complete; the worker refreshes it hourly.
insert into support_source_sync (source, last_complete_at) values ('bizinfo', now());

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
      and (
        p.source <> 'bizinfo'
        or p.application_end is not null
        or exists (
          select 1
          from support_source_sync s
          where s.source = 'bizinfo'
            and s.last_complete_at >= now() - interval '3 days'
        )
      )
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
