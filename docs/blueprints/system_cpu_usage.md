# System: high CPU usage

[Back to blueprint index](README.md)

Detects sustained CPU usage on the Home Assistant host or compatible devices,
including device sensors whose entity IDs use a supported suffix.

## Default behavior

| Setting | Value |
| --- | --- |
| Blueprint ID | `system_cpu_usage` |
| Blueprint version | 2 |
| Source | Value (`value`) |
| Condition | Strictly above 90% |
| Duration | 300 seconds (5 minutes) |

Each selected sensor must stay above 90% for five minutes before its alert becomes
active. A reading of exactly 90% does not match. A valid reading at or below the
threshold clears the condition; a shorter spike does not become an active alert.

## Compatible entities

The entity must be a `sensor`, report `%`, and not belong to the `hassio`
(Supervisor) integration. It must also match either of these paths:

- **System Monitor** (`systemmonitor`): translation key `processor_use`, unique ID
  `processor_use`, or unique ID matching `processor_use_*`.
- **Entity ID**, from any integration other than `hassio`, matching one of:
  `sensor.*_cpu_utilization`, `sensor.*_cpu_usage`, `sensor.*_processor_use`, or
  `sensor.*_utilisation_du_processeur`.

For example, `sensor.router_cpu_utilization` reporting `%` can match. System
Monitor registry matching continues to work when its entity ID is renamed.
Other device sensors must retain a supported entity-ID suffix.

## Adjustments and limitations

Review the generated entity list and adapt the threshold and delay to your devices.
One rule shares these settings across its entities; use separate custom rules for
devices requiring different thresholds.

Supervisor app/add-on sensors are deliberately excluded, even with a matching
name and unit. Load-average sensors and values expressed as a fraction rather than
`%` are not selected. Missing or nonnumeric readings are not evidence of high CPU
usage; use automatic availability monitoring for outages.

[Blueprint source](../../custom_components/alert_manager/blueprint/system/system_cpu_usage.yaml)
