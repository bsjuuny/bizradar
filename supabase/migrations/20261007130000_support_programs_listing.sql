-- Support Radar 목록용 뷰. 기업마당 사본(duplicate_of가 있는 행)을 숨길지는 저장된 표시만으로
-- 정하지 않고, 조회하는 순간 그 원본(K-Startup 행)의 상태로 정한다. 그래서 각 행에 원본의
-- 지금 상태를 붙여 준다:
--   original_open - 원본이 지금 "모집 중"인가: recruiting이고 마감일이 없거나 오늘(서울)
--                   이후. 웹 기본 보기(apps/web/src/lib/supportPrograms.ts)와 같은 정의다.
--   original_end  - 원본의 마감일("7일 안에 마감" 보기에서 원본도 보이는지 판단할 때 쓴다).
-- duplicate_of는 워커가 매시간 맞추는 짝(pair)일 뿐이고, 원본이 마감되거나 마감일이 지나는
-- 순간부터 사본이 다시 보인다 - 다음 워커 실행을 기다리지 않는다. 사본을 숨기는 조건은 웹이
-- 보기마다 정한다(docs/SUPPORT_PROGRAMS.md#web).
--
-- security_invoker: 조회하는 사용자의 RLS를 그대로 적용한다(opportunities_current와 같은 방식).
-- application_end는 날짜의 자정(UTC)으로 저장되므로, 오늘(서울) 날짜도 같은 방식으로 바꿔 비교한다.
-- 주의: p.* 는 이 뷰를 만들 때의 컬럼 목록으로 고정된다. support_programs에 컬럼을 더하는
-- 마이그레이션은 이 뷰도 다시 만들어야(drop + create) 웹에서 그 컬럼을 읽을 수 있다.

create view support_programs_listing
  with (security_invoker = true)
  as
  select
    p.*,
    (
      o.recruiting is true
      and (
        o.application_end is null
        or o.application_end >= ((now() at time zone 'Asia/Seoul')::date)::timestamp at time zone 'UTC'
      )
    ) as original_open,
    o.application_end as original_end
  from support_programs p
  left join support_programs o on o.id = p.duplicate_of;

grant select on support_programs_listing to authenticated;
