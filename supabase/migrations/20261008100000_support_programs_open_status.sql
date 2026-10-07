-- "모집 중"과 중복 숨김을 다듬는다 (20261007130000의 is_open과 list_support_programs를 바꾼다 -
-- 그 파일은 이미 적용돼서 고치지 않는다).
--
-- 1. is_open(support_programs): 행 자기 값만 본다 - 중복 짝(duplicate_of)은 상태를 바꾸지
--    않는다. 짝짓기는 제목 유사도로 하는 추정이라, 그게 틀렸을 때 기업마당이 모집 중이라고
--    올려 둔 공고를 "마감"으로 만들면 안 된다(놓친 기회가 중복 한 줄보다 비싸다).
--    a. 모집 여부도 마감일도 없으면 NULL(모름) - "마감"이라고 단정하지 않는다. 상세의
--       모집상태는 "—", 마감 칸은 신청기간 문장이나 "일정 미정"이고, 모집 중 목록에는 들지
--       않는다.
--    b. "3일 넘게 목록에 없으면 마감"은 날짜 없는 행에만 적용한다. 그 규칙은 마감 처리가
--       멈췄을 때(키 만료, 계속 불완전한 응답) 날짜로는 영원히 닫히지 않는 공고를 위한
--       것이고, 날짜가 있는 공고는 날짜로 닫힌다 - 워커 PC가 사흘 꺼져 있었다고 마감일이
--       몇 주 남은 공고가 "마감"으로 보이면 안 된다. K-Startup은 last_seen_at을 추적하지
--       않는다(NULL) - 2026-10-08 실측 저장된 1,072건 모두 마감일이 있어 날짜로 닫힌다.
-- 2. list_support_programs의 중복 숨김: 원본(K-Startup)과 그 사본들(duplicate_of가 원본을
--    가리키는 기업마당 행 - 공고와 재공고처럼 둘 이상일 수 있다, 2026-10-08 실측 1건)은 한
--    묶음이고, 결과에 든 묶음은 한 줄로 보인다: 모집 중인 행이 먼저, 그 안에서 원본이
--    먼저. 원본과 사본이 둘 다 모집 중이면 원본, 사본만 모집 중이면 그 사본, 둘 다 마감이면
--    원본. 그래서 어느 보기(모집 중 / 마감 포함 전체)에서든 한 프로그램은 한 줄이고, 그
--    줄의 상태가 보기마다 다르지 않다. 워커는 마감된 짝도 짝으로 둔다
--    (worker/dedupe/support_programs.py plan_duplicate_marks).
-- 3. list_support_programs: 모집 여부를 모르는 공고(NULL)는 모집 중인 공고 다음, 마감된
--    공고 앞에 온다 - 아직 모집 중일 수도 있어서 마감 이력 맨 끝에 묻히면 안 된다.
--    open/closing에서는 is_open을 계산하기 전에 그 필요조건(마감이라고 하지 않았고 마감일이
--    지나지 않음)으로 먼저 거른다 - 정의는 여전히 is_open 하나이고, 마감된 이력(매달 ~1,500건씩
--    쌓인다)에 is_open을 계산하지 않으려는 것뿐이다. "마감 포함 전체"는 전체를 센다 - 2026-10-08
--    기준 ~2,500행이라 요청마다 수 ms이고, 몇 년 동안은 그대로다.
-- 4. 기업마당 행은 last_seen_at이 반드시 있다(check). is_open은 NULL을 "추적하지 않음"
--    (K-Startup)으로 건너뛰는데, 기업마당 행이 NULL이면 그 규칙을 빠져나간다. 워커는 2026-10-07
--    배포부터 upsert마다 값을 쓰고, 2026-10-08 실측 1,473건 모두 값이 있다.
--
-- The 3 days must stay well above the worker's refresh interval for last_seen_at
-- (LAST_SEEN_REFRESH_AFTER in worker/repositories/support_programs.py) -
-- worker/tests/test_support_programs_repository.py reads this file to check it.

alter table support_programs
  add constraint support_programs_bizinfo_last_seen
  check (source <> 'bizinfo' or last_seen_at is not null);

-- create or replace keeps the existing grants/revokes (20261007140000, 20261007150000).
create or replace function is_open(p support_programs)
  returns boolean
  language sql
  stable
  as $$
    select case
      when p.recruiting is null and p.application_end is null then null
      else coalesce(p.recruiting, true)
        and (p.application_end is null or p.application_end >= support_program_today_utc())
        and (
          p.application_end is not null
          or p.last_seen_at is null
          or p.last_seen_at >= now() - interval '3 days'
        )
    end
  $$;

create or replace function list_support_programs(
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
          -- A necessary condition of is_open (see the header), checked first.
          and (
            p_status = 'all'
            or (
              p.recruiting is distinct from false
              and (p.application_end is null or p.application_end >= support_program_today_utc())
            )
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
      grouped as (
        -- One row per original and its copies (see the header): open rows first, then
        -- the original, then the lowest id.
        select
          f.*,
          row_number() over (
            partition by coalesce(f.duplicate_of, f.id)
            order by (f.is_open is true) desc, (f.duplicate_of is null) desc, f.id
          ) as rank_in_group
        from filtered f
      ),
      visible as (
        select g.*
        from grouped g
        where g.rank_in_group = 1
      ),
      ordered as (
        select
          v.*,
          row_number() over (
            order by
              case when v.is_open then 0 when v.is_open is null then 1 else 2 end,
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
