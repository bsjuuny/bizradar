-- Support Radar "IT 관련만" 필터용 분류 컬럼. investment_linked와 같은 방식이다: 워커가 수집할
-- 때 규칙(worker/ai/support_it_filter.py)으로 계산해 저장하고, 웹은 읽기만 한다.
-- 기존 행은 기본값 false로 시작하므로, 이 마이그레이션 뒤에 재분류를 한 번 돌려야 한다:
--   python -m worker.jobs.support_reclassify
-- 자세한 내용은 docs/SUPPORT_PROGRAMS.md#it-filter.

alter table support_programs
  add column it_related boolean not null default false;

create index support_programs_it_related_idx on support_programs (it_related)
  where it_related;
