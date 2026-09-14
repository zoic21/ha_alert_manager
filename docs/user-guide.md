# Alert Manager documentation

[Back to the project](../README.md)

The detailed documentation is maintained in English. Start with the page that matches what you want to configure or understand.

| Guide | Contents |
| --- | --- |
| [Custom rules](custom-rules.md) | States and attributes, comparisons, Jinja, inactivity, variations, transitions, rule testing and YAML examples. |
| [Configuration](configuration.md) | Automatic monitoring packs, delays and exclusions, notification profiles, labels, YAML, configuration backups and diagnostics. |
| [Configuration coherence](coherence.md) | Reference scans, missing entities and ZHA devices, exclusions, scheduling and the optional coherence alert. |
| [Dashboard and history](dashboard-and-history.md) | Overview, dashboard card, filters, acknowledgement, startup behavior, history and recurrence statistics. |

## Getting started

Install and add the integration using the [installation instructions](../README.md#installation), then review **Configuration → Automatic monitoring**. Adjust the packs to your installation before adding custom rules. Built-in notification profiles are optional.

The [dashboard and history guide](dashboard-and-history.md) explains how to review and acknowledge the resulting alerts. The [custom rules guide](custom-rules.md#examples) includes examples to adapt to your own entity IDs.

## Access and documentation scope

Authenticated users can view the dashboard card, Overview, History and their details. Configuration, other tabs and all actions require an administrator.

Documentation follows the branch you are reading. Use the matching release branch or tag when looking up an installed version; development-branch options may not exist in a stable release.
