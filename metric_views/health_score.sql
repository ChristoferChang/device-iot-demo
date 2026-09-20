-- Metric view: per-machine risk scores for "which machines are at risk?" style questions.
CREATE OR REPLACE VIEW sbr_iot_demo.fleet.health_score
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: sbr_iot_demo.fleet.gold_health_score
  comment: "Per-machine risk score (0 healthy to 100 critical) with contributing signals"
  dimensions:
    - name: Equipment ID
      expr: equipment_id
      synonyms: [unit, machine, asset, equipment]
    - name: Equipment Class
      expr: equipment_class
      synonyms: [class, machine class]
  measures:
    - name: At-Risk Machines
      expr: COUNT(1) FILTER (WHERE health_risk_score > 0)
      synonyms: [at risk units, machines needing attention]
      comment: "Machines with any active risk signal"
    - name: Critical Machines
      expr: COUNT(1) FILTER (WHERE health_risk_score >= 40)
      comment: "Machines with a severe risk signal"
    - name: Avg Risk Score
      expr: AVG(health_risk_score)
      comment: "Mean risk score across machines in scope"
    - name: Max Risk Score
      expr: MAX(health_risk_score)
      comment: "Worst risk score in scope"
    - name: Avg Running Battery Voltage
      expr: AVG(min_battery_running_7d)
      comment: "Mean of per-machine minimum running battery voltage (7d)"
    - name: Avg Engine Hours
      expr: AVG(engine_hours_latest)
$$;
