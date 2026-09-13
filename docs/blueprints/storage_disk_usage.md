# Storage: high disk usage

[Back to blueprint index](README.md)

Detects sustained high disk usage for the disks or mount points exposed by the
Home Assistant System Monitor integration.

## Default behavior

| Setting | Value |
| --- | --- |
| Blueprint ID | `storage_disk_usage` |
| Blueprint version | 1 |
| Source | Value (`value`) |
| Condition | Strictly above 90% |
| Duration | 300 seconds (5 minutes) |

Each selected sensor must stay above 90% for five minutes before its alert becomes
active. Exactly 90% does not match. A valid reading at or below the threshold
clears the condition; a shorter spike does not become an active alert.

## Compatible entities

**System Monitor** (`systemmonitor`) must be configured. Enable the disk usage
percentage sensors for the mount points you want to monitor.

An entity must belong to System Monitor, be a `sensor`, report `%`, and have one
of the following registry identities:

- Translation key `disk_use_percent`.
- Unique ID `disk_use_percent`.
- Unique ID matching `disk_use_percent_*`.

Entity-ID renaming does not prevent matching when the registry identity remains
compatible. All matching enabled sensors are included in one rule, with an
independent alert condition for each sensor.

## Adjustments and limitations

Edit the threshold, delay and entity list after generation. Separate rules allow
different limits for different volumes.

This blueprint does not discover disks directly. It only uses the sensors exposed
by System Monitor. NAS sensors from other integrations, free-space sensors and
values reported in bytes or GiB are not selected. A similar entity name alone is
insufficient. Missing or nonnumeric readings are not evidence of a full disk;
monitor availability separately.

[Blueprint source](../../custom_components/alert_manager/blueprint/storage/storage_disk_usage.yaml)
