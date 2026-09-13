# System: high memory usage

[Back to blueprint index](README.md)

Detects sustained high memory usage on System Monitor and compatible device sensors.

## Default behavior

| Setting | Value |
| --- | --- |
| Blueprint ID | `system_memory_usage` |
| Blueprint version | 2 |
| Source | Value (`value`) |
| Condition | Strictly above 90% |
| Duration | 300 seconds (5 minutes) |

Each selected sensor must stay above 90% for five minutes before its alert becomes
active. Exactly 90% does not match. A valid reading at or below the threshold
clears the condition; a shorter spike does not become an active alert.

## Compatible entities

The entity must be a `sensor`, report `%`, and not belong to the `hassio`
(Supervisor) integration. It must also match either of these paths:

- **System Monitor** (`systemmonitor`): translation key `memory_use_percent`,
  unique ID `memory_use_percent`, or unique ID matching `memory_use_percent_*`.
- **Entity ID**, from any integration other than `hassio`, matching one of:
  `sensor.*_memory_utilization`, `sensor.*_memory_usage`,
  `sensor.*_memory_use_percent`, or `sensor.*_utilisation_de_la_memoire`.

For example, `sensor.router_memory_utilization` reporting `%` can match. Renamed
System Monitor entities can still match through their registry metadata. Other
device sensors must retain a supported entity-ID suffix.

## Adjustments and limitations

Check what the source sensor counts as used memory, especially whether it includes
reclaimable caches, before choosing a threshold. Edit the generated rule to change
its threshold, delay or entity list. Use separate rules for different device limits.

Sensors reporting bytes, MiB or GiB are not selected. Supervisor app/add-on sensors
are excluded even if their names and units match. Missing or nonnumeric readings
are not evidence of high memory usage; monitor availability separately.

[Blueprint source](../../custom_components/alert_manager/blueprint/system/system_memory_usage.yaml)
