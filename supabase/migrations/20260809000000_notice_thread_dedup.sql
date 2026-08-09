-- Notice-thread tracking: G2B issues a brand new bidNtceNo when an agency cancels and
-- re-announces (재공고, linked back via befBidBbancNo), and increments bidNtceOrd under
-- the SAME bidNtceNo for corrections (변경공고). Both were already present in
-- raw_payload but never normalized into their own columns, so Project Radar had no way
-- to show only the current/live state of a notice instead of every historical revision -
-- found live: the same underlying procurement appeared as up to 4 separate rows. See
-- docs/DATA_PIPELINE.md and docs/TROUBLESHOOTING.md.

alter table opportunities
  add column bid_ntce_no text,
  add column bid_ntce_ord int,
  add column ntce_kind_nm text;

create index opportunities_bid_ntce_no_ord_idx on opportunities (bid_ntce_no, bid_ntce_ord desc);

-- Shows only the current state of each G2B notice thread: the latest bidNtceOrd within
-- each bidNtceNo, excluding threads whose latest revision is a cancellation (취소공고) -
-- a cancelled thread's live successor (if any) is a different bidNtceNo and already its
-- own separate row. Rows with bid_ntce_no null (not yet backfilled, or a future
-- non-G2B source with no notion of this) pass through unfiltered rather than being
-- silently dropped. `security_invoker` makes the view apply the querying user's own RLS
-- instead of the view owner's - it's a passthrough of `opportunities`, not a separate
-- data source, so it must stay gated the same way (any authenticated user can read).
create view opportunities_current
  with (security_invoker = true)
  as
  select o.*
  from opportunities o
  where o.bid_ntce_no is null
  union all
  select o.*
  from opportunities o
  join (
    select bid_ntce_no, max(bid_ntce_ord) as latest_ord
    from opportunities
    where bid_ntce_no is not null
    group by bid_ntce_no
  ) latest
    on o.bid_ntce_no = latest.bid_ntce_no
   and o.bid_ntce_ord = latest.latest_ord
  where o.ntce_kind_nm is distinct from '취소공고';

grant select on opportunities_current to authenticated;
