# System: high CPU temperature

[Back to blueprint index](README.md)

Detects sustained high processor temperature on System Monitor and compatible
device sensors reporting Celsius.

## Default behavior

| Setting | Value |
| --- | --- |
| Blueprint ID | `system_cpu_temperature` |
| Blueprint version | 2 |
| Source | Value (`value`) |
| Condition | Strictly above 80 °C |
| Duration | 300 seconds (5 minutes) |

Each selected sensor must stay above 80 °C for five minutes before its alert becomes
active. Exactly 80 °C does not match. A valid reading at or below the threshold
clears the condition; a shorter spike does not become an active alert.

## Compatible entities

The entity must be a `sensor`, report exactly `°C`, and not belong to the `hassio`
(Supervisor) integration. It must also match either of these paths:

- **System Monitor** (`systemmonitor`): translation key `processor_temperature`,
  unique ID `processor_temperature`, or unique ID matching
  `processor_temperature_*`.
- **Entity ID**, from any integration other than `hassio`, matching one of:
  `sensor.*_cpu_temperature`, `sensor.*_processor_temperature`,
  `sensor.*_temperature_cpu`, or `sensor.*_temperature_du_processeur`.

For example, `sensor.server_cpu_temperature` reporting `°C` can match. Renamed
System Monitor entities can still match through registry metadata; other device
sensors must retain a supported suffix.

## Adjustments and limitations

Adapt the threshold to the processor and its operating limits. The generated rule
uses a numeric threshold, without automatic unit conversion. Fahrenheit sensors
are deliberately excluded; use a separate rule with the appropriate threshold if
you need to monitor them.

Room-temperature sensors are not selected merely because their device class is
temperature. Supervisor app/add-on sensors are excluded. Missing or nonnumeric
readings are not evidence of overheating; monitor availability separately.

[Blueprint source](../../custom_components/alert_manager/blueprint/system/system_cpu_temperature.yaml)
