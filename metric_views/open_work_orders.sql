-- Metric view: open work orders — the "action" side of the loop; updates live as
-- the create_work_order procedure writes rows.
CREATE OR REPLACE VIEW sbr_iot_demo.fleet.open_work_orders
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: sbr_iot_demo.fleet.work_orders
  filter: status = 'OPEN'
  comment: "Open work orders created via the create_work_order action tool"
  dimensions:
    - name: Equipment ID
      expr: equipment_id
      synonyms: [unit, machine, asset]
    - name: Priority
      expr: priority
    - name: Created Date
      expr: "CAST(created_at AS DATE)"
      synonyms: [day, date]
    - name: Created By
      expr: created_by
  measures:
    - name: Open Work Orders
      expr: COUNT(1)
      synonyms: [open orders, work orders count, tickets]
      comment: "Count of work orders currently open"
$$;
