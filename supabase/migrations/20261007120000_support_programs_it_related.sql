-- Support Radar "IT 관련만" 필터용 분류 컬럼. investment_linked와 같은 방식이다: 워커가 수집할
-- 때 규칙(worker/ai/support_it_filter.py)으로 계산해 저장하고, 웹은 읽기만 한다.
-- 기존 행은 기본값 false로 시작하므로, 이 마이그레이션 뒤에 재분류를 한 번 돌려야 한다:
--   python -m worker.jobs.support_reclassify
-- 인덱스는 두지 않는다: 유일한 독자인 list_support_programs가 "not p_it_only or it_related"
-- 형태로 거르는 범용 계획이라 부분 인덱스를 쓰지 않고, 쓰기 비용만 늘린다.
-- 자세한 내용은 docs/SUPPORT_PROGRAMS.md#it-filter.

alter table support_programs
  add column it_related boolean not null default false;
