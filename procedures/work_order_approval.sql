-- Human-in-the-loop work-order flow (Act 4, revised 2026-09-19).
-- propose_work_order: agent writes a PENDING_APPROVAL row + alerts the district
-- manager; approve_work_order: human approval flips it to OPEN with an audit
-- suffix. Both SQL SECURITY INVOKER — the caller's UC privileges govern the write
-- (Genie's read-only session cannot do DML, so the calling agent/app executes
-- these with its own connection).
-- Verified live 2026-09-19: WO-20260919183602-218149 proposed (demo-agent) then
-- approved (chris.chang@databricks.com) -> OPEN with audit suffix.

CREATE OR REPLACE PROCEDURE sbr_iot_demo.fleet.propose_work_order(
  IN equipment_id STRING,
  IN priority STRING,
  IN notes STRING,
  IN proposed_by STRING
)
SQL SECURITY INVOKER
LANGUAGE SQL
BEGIN
  INSERT INTO sbr_iot_demo.fleet.work_orders
  SELECT concat('WO-', date_format(current_timestamp(), 'yyyyMMddHHmmss'), '-',
                substring(crc32(concat(equipment_id, coalesce(notes, ''))), 1, 6)),
         equipment_id, upper(priority), 'PENDING_APPROVAL', notes, proposed_by,
         current_timestamp();
END;

-- approve_work_order: params use the p_ prefix — bare params that match column
-- names (order_id) are shadowed by the column in the UPDATE WHERE clause, which
-- made "w.order_id = order_id" always true and approved EVERY pending row
-- (bug found live 2026-09-20). Positional CALL signature unchanged.
CREATE OR REPLACE PROCEDURE sbr_iot_demo.fleet.approve_work_order(
  IN p_order_id STRING,
  IN p_approved_by STRING
)
SQL SECURITY INVOKER
LANGUAGE SQL
BEGIN
  UPDATE sbr_iot_demo.fleet.work_orders AS w
  SET status = 'OPEN', notes = concat(notes, ' | approved by ', p_approved_by)
  WHERE w.order_id = p_order_id AND w.status = 'PENDING_APPROVAL';
END;
