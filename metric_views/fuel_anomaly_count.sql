-- Metric view: fuel anomalies (theft/leak pattern — abnormal mid-tick drops).
CREATE OR REPLACE VIEW sbr_iot_demo.fleet.fuel_anomaly_count
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: sbr_iot_demo.fleet.gold_events
  filter: event_type = 'FUEL_ANOMALY'
  comment: "Fuel anomalies: abnormal fuel drops between consecutive telemetry ticks"
  dimensions:
    - name: Equipment ID
      expr: equipment_id
      synonyms: [unit, machine, asset]
    - name: Equipment Class
      expr: equipment_class
    - name: Anomaly Day
      expr: "CAST(event_ts AS DATE)"
      synonyms: [day, date]
  measures:
    - name: Fuel Anomalies
      expr: COUNT(1)
      synonyms: [anomaly count, fuel theft events, fuel anomalies count]
      comment: "Number of abnormal fuel-drop events"
    - name: Avg Drop Points
      expr: AVG(metric_value)
      comment: "Average fuel-percentage drop per anomaly"
$$;
