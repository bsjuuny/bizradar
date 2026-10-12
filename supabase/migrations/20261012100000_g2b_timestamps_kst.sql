-- G2B posted_at / bid_close_at / open_at: store the real instant, not KST wall-clock as UTC.
--
-- G2B sends bidNtceDt / bidClseDt / opengDt as KST strings with no offset. The collector
-- parsed them naive and Postgres read the naive ISO string as UTC, so every stored G2B
-- time was nine hours late: a 12:00 KST deadline displayed as 21:00, the queue kept a
-- notice "open" for nine hours after it closed, and match scoring saw nine extra hours.
-- worker/collectors/g2b.py now parses them as Asia/Seoul (same change as this migration);
-- this rewrites the rows written before that.
--
-- Re-derived from raw_payload, and only where the stored value is exactly the raw string
-- read as UTC (the old bug), so it is idempotent and never touches a row the fixed
-- collector already wrote correctly. Checked before writing it (2026-10-12): 27,764 g2b
-- rows, every one of them in the old form for every non-null column - posted_at 27,764,
-- bid_close_at 24,261 (3,503 null), open_at 27,764 - with none already correct and none
-- matching neither form. One statement so each row is rewritten once (one updated_at
-- bump, one dead tuple); nothing reads opportunities.updated_at.

with raw as (
  select
    id,
    case when raw_payload->>'bidNtceDt' ~ '^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?$'
      then (raw_payload->>'bidNtceDt')::timestamp end as notice_kst,
    case when raw_payload->>'bidClseDt' ~ '^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?$'
      then (raw_payload->>'bidClseDt')::timestamp end as close_kst,
    case when raw_payload->>'opengDt' ~ '^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?$'
      then (raw_payload->>'opengDt')::timestamp end as open_kst
  from public.opportunities
  where source = 'g2b'
)
update public.opportunities o
set
  posted_at = case when (o.posted_at at time zone 'UTC') = r.notice_kst
    then r.notice_kst at time zone 'Asia/Seoul' else o.posted_at end,
  bid_close_at = case when (o.bid_close_at at time zone 'UTC') = r.close_kst
    then r.close_kst at time zone 'Asia/Seoul' else o.bid_close_at end,
  open_at = case when (o.open_at at time zone 'UTC') = r.open_kst
    then r.open_kst at time zone 'Asia/Seoul' else o.open_at end
from raw r
where o.id = r.id
  and (
    (o.posted_at at time zone 'UTC') = r.notice_kst
    or (o.bid_close_at at time zone 'UTC') = r.close_kst
    or (o.open_at at time zone 'UTC') = r.open_kst
  );
