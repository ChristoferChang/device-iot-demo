-- Metric view: fleet utilization + daily operating KPIs by equipment class.
CREATE OR REPLACE VIEW sbr_iot_demo.fleet.fleet_utilization
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: sbr_iot_demo.fleet.gold_daily_agg
  comment: "Fleet utilization trend and daily operating KPIs by equipment class"
  dimensions:
    - name: Equipment Class
      expr: equipment_class
      synonyms: [class, machine class, vehicle class]
      comment: "Generator, aerial lift, excavator, or compressor"
    - name: Day
      expr: day
      synonyms: [date]
      comment: "Calendar day of telemetry"
  measures:
    - name: Machines Reporting
      expr: SUM(machines_reporting)
      comment: "Distinct machines with telemetry that day"
    - name: Avg Utilization
      expr: AVG(utilization_pct)
      synonyms: [utilization, uptime, usage rate]
      comment: "Share of 5-min ticks with engine running (0-1)"
    - name: Avg Fuel Level
      expr: AVG(avg_fuel_pct)
      comment: "Average fuel level percent across machines"
    - name: Avg Battery Voltage
      expr: AVG(avg_battery_voltage)
$$;
