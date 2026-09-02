import assert from "node:assert/strict";
import test from "node:test";

import { renderAutomatic } from "../frontend-src/views/automatic.js";
import {
  renderBackupRestoreDialog, renderConfigBackups,
} from "../frontend-src/components/config-backups.js";
import { renderConfigurationDrawer } from "../frontend-src/components/configuration-drawer.js";
import { MDI_CLOSE } from "../frontend-src/utils/constants.js";
import {
  renderCoherence, renderDeletedEntitiesDrawer,
} from "../frontend-src/views/coherence.js";
import { renderHistory } from "../frontend-src/views/history.js";
import { renderOverview } from "../frontend-src/views/overview.js";
import { renderSettings } from "../frontend-src/views/settings.js";

const t = (key) => key;

test("overview rendering uses only its explicit view context", () => {
  let tableCall;
  const markup = renderOverview({
    alerts: {
      active_count: 2,
      pending_count: 1,
      acknowledge_count: 3,
      tracked_count: 20,
    },
    selectedStatuses: ["active"],
    pageMessages: "<ha-alert>notice</ha-alert>",
    rows: [{ id: "alert-1" }],
    renderAlertTable: (...args) => {
      tableCall = args;
      return `<table-view>${args[2]}</table-view>`;
    },
    t,
  });

  assert.equal(tableCall[0], "overview");
  assert.deepEqual(tableCall[1], [{ id: "alert-1" }]);
  assert.match(markup, /data-summary="active"[^>]*aria-pressed="true"/);
  assert.match(markup, /<strong class="danger">2<\/strong>/);
  assert.match(markup, /<strong>20<\/strong>/);
});

test("history rendering handles enabled and disabled states without panel state", () => {
  const disabled = renderHistory({
    limit: 0,
    events: [],
    pageMessages: "",
    rows: [],
    renderAlertTable() { throw new Error("table must not render"); },
    t,
  });
  assert.match(disabled, /history.disabled_title/);

  const enabled = renderHistory({
    limit: 100,
    events: [{ id: "event-1" }],
    pageMessages: "<messages></messages>",
    rows: [{ id: "row-1" }],
    renderAlertTable: (kind, rows, header) => `${kind}:${rows[0].id}:${header}`,
    t,
  });
  assert.equal(enabled, "history:row-1:<messages></messages>");
});

test("coherence rendering receives scan state and statistics explicitly", () => {
  const empty = renderCoherence({
    result: null,
    loading: true,
    pageMessages: "",
    statsMarkup: "",
    t,
  });
  assert.match(empty, /data-action="scan-coherence" disabled/);
  assert.match(empty, /coherence.scanning/);
  assert.match(empty, /appearance="outlined" data-action="open-deleted-entities"/);

  const scanned = renderCoherence({
    result: { issue_count: 1 },
    loading: false,
    pageMessages: "<ha-alert>ok</ha-alert>",
    statsMarkup: "<strong>1</strong>",
    t,
  });
  assert.match(scanned, /data-coherence-table-page/);
  assert.match(scanned, /<strong>1<\/strong>/);
});

test("deleted entity drawer renders retained registry entries safely", () => {
  const markup = renderDeletedEntitiesDrawer({
    data: {
      entities: [{
        entity_id: "sensor.deleted_<unsafe>",
        name: "Old sensor",
        platform: "test",
        deleted_at: "2026-08-24T12:00:00+00:00",
      }],
    },
    loading: false,
    error: null,
    formatDate: () => "24/08/2026 12:00:00",
    t,
  });

  assert.match(markup, /class="side-drawer deleted-entities-drawer"/);
  assert.match(markup, /sensor\.deleted_&lt;unsafe&gt;/);
  assert.match(markup, /Old sensor/);
  assert.match(markup, /24\/08\/2026 12:00:00/);
  assert.doesNotMatch(markup, /sensor\.deleted_<unsafe>/);
});

test("mobile drawers use Home Assistant's resizable bottom sheet", () => {
  const configuration = renderConfigurationDrawer({
    title: "Configuration",
    ariaLabel: "Fermer",
    content: "<div>Contenu</div>",
    saveAction: "save-settings",
    saveLabel: "Enregistrer",
    busy: false,
    useBottomSheet: true,
  });
  const deletedEntities = renderDeletedEntitiesDrawer({
    data: { entities: [] },
    loading: false,
    error: null,
    formatDate: (value) => value,
    useBottomSheet: true,
    t,
  });

  for (const markup of [configuration, deletedEntities]) {
    assert.match(markup, /^<ha-resizable-bottom-sheet/);
    assert.match(markup, /class="side-drawer-bottom-sheet"/);
    assert.doesNotMatch(markup, /side-drawer-backdrop/);
  }
  assert.match(configuration, /data-close-action="close-configuration-drawer"/);
  assert.match(deletedEntities, /data-close-action="close-deleted-entities"/);
});

test("automatic rendering uses prepared configuration and draft data", () => {
  const pack = {
    id: "battery",
    available: true,
    translation_key: "battery",
    config_fields: [
      {
        id: "threshold",
        type: "number",
        translation_key: "threshold",
        default: 15,
        unit: "%",
      },
      {
        id: "device_thresholds",
        type: "device_number_map",
        translation_key: "device_thresholds",
        unit: "%",
      },
    ],
  };
  const markup = renderAutomatic({
    availablePacks: [pack],
    config: {
      automatic: {
        battery: {
          enabled: true,
          delay: 60,
          threshold: 15,
          device_thresholds: { "device-1": 15 },
        },
      },
    },
    draft: {
      battery: {
        threshold: 15,
        device_thresholds: [{ target_id: "device-1", value: 15 }],
      },
    },
    configurationDrawer: { kind: "automatic", id: "battery" },
    busy: false,
    renderNumberField: (id, label, value) => `<number id="${id}">${label}:${value}</number>`,
    t,
  });

  assert.match(markup, /auto-battery-enabled[^>]*checked/);
  assert.match(markup, /auto-battery-delay/);
  assert.match(markup, /auto-battery-threshold[^>]*>automatic\.fields\.threshold\.label:15/);
  assert.match(markup, /auto-battery-configuration/);
  assert.match(markup, /automatic-configuration-entry/);
  assert.match(markup, /class="side-drawer configuration-drawer"/);
  assert.match(markup, /auto-battery-device_thresholds-target-0/);
  assert.match(markup, /value="15"/);
  assert.match(markup, /pack-map-heading[\s\S]*data-action="add-pack-map-row"/);
  const drawerMarkup = markup.slice(markup.indexOf("configuration-drawer-backdrop"));
  assert.doesNotMatch(drawerMarkup, /auto-battery-threshold/);

  const automationErrors = renderAutomatic({
    availablePacks: [{
      id: "execution_errors",
      available: true,
      translation_key: "execution_errors",
      config_fields: [{
        id: "failure_thresholds",
        type: "entity_number_map",
        translation_key: "failure_thresholds",
        minimum: 1,
        maximum: 100,
        step: 1,
        entity_domains: ["automation", "script"],
      }],
    }],
    config: {
      automatic: {
        execution_errors: {
          enabled: true,
          delay: 0,
          failure_thresholds: { "automation.test": 3 },
        },
      },
    },
    draft: {
      execution_errors: {
        failure_thresholds: [{ target_id: "automation.test", value: 3 }],
      },
    },
    configurationDrawer: { kind: "automatic", id: "execution_errors" },
    busy: false,
    renderNumberField: (id) => `<number id="${id}"></number>`,
    t,
  });
  assert.match(automationErrors, /packs\.execution_errors\.name/);
  assert.match(automationErrors, /auto-execution_errors-enabled[^>]*checked/);
  assert.match(automationErrors, /auto-execution_errors-delay/);
  assert.match(automationErrors, /auto-execution_errors-failure_thresholds-target-0/);
  assert.match(automationErrors, /value="3"/);
});

test("settings rendering consumes prepared drafts without initializing them", () => {
  const markup = renderSettings({
    config: { global_delay: 900, pending_display_delay: 10 },
    settingsDraft: {
      coherence_scan_esphome: true,
      coherence_ignored_entity_references: ["sensor.old"],
      excluded_labels: [],
      excluded_entities: [],
      excluded_devices: [],
    },
    historyConfig: { retention_limit: 100 },
    historyEvents: [{ id: "event-1" }],
    entityDelayDraft: [{ entity_id: "sensor.test", delay: 60 }],
    ignoredReferenceDraft: "sensor.new",
    configurationDrawer: { kind: "settings", id: "entity_delays" },
    busy: false,
    renderNumberField: (id, label, value) => `<number id="${id}">${label}:${value}</number>`,
    t,
  });

  assert.match(markup, /id="global-delay"/);
  assert.match(markup, /coherence-scan-esphome[^>]*checked/);
  assert.match(markup, /data-ignored-reference="sensor.old"/);
  assert.match(markup, /value="sensor.new"/);
  assert.match(markup, /settings-entity_delays-configuration/);
  assert.match(markup, /class="side-drawer configuration-drawer"/);
  assert.match(markup, new RegExp(`ha-icon-button[^>]*path="${MDI_CLOSE}"`));
  assert.match(markup, /configuration-section-heading[\s\S]*data-action="add-entity-delay"[\s\S]*class="delay-list"/);
  assert.match(markup, /data-delay-index="0"[^>]*value="60"/);
});

test("automatic backups stay in settings without a recovery banner", () => {
  const backups = [
    { id: "one", created_at: "2026-08-30T03:00:00+00:00", rules: 18 },
    { id: "two", created_at: "2026-08-29T03:00:00+00:00", rules: 18 },
    { id: "three", created_at: "2026-08-28T03:00:00+00:00", rules: 17 },
  ];
  const backupsMarkup = renderConfigBackups({
    backups,
    busy: false,
    date: (value) => value,
    t,
  });
  const overview = renderOverview({
    alerts: {
      active_count: 0, pending_count: 0, acknowledge_count: 0, tracked_count: 0,
    },
    selectedStatuses: [],
    pageMessages: "",
    rows: [],
    renderAlertTable: (_kind, _rows, summary) => summary,
    t,
  });
  const settings = renderSettings({
    config: { global_delay: 900, pending_display_delay: 10 },
    settingsDraft: {
      coherence_scan_esphome: true,
      coherence_ignored_entity_references: [],
    },
    historyConfig: { retention_limit: 100 },
    historyEvents: [],
    entityDelayDraft: [],
    ignoredReferenceDraft: "",
    busy: false,
    configBackupsMarkup: backupsMarkup,
    renderNumberField: () => "",
    t,
  });

  assert.equal((backupsMarkup.match(/data-backup-id=/g) ?? []).length, 9);
  assert.match(backupsMarkup, /download-config-backup/);
  assert.match(backupsMarkup, /restore-config-backup/);
  assert.ok(settings.includes(backupsMarkup));
  assert.doesNotMatch(overview, /data-config-recovery|download-failed-config/);
});

test("backup restoration uses a native confirmation dialog", () => {
  const markup = renderBackupRestoreDialog({
    backup: { id: "backup-1", created_at: "2026-08-30T03:00:00+00:00", rules: 18 },
    busy: false,
    date: (value) => value,
    t,
  });

  assert.match(markup, /^<ha-dialog/);
  assert.match(markup, /<ha-dialog-header>/);
  assert.match(markup, /data-action="cancel-config-backup-restore"/);
  assert.match(markup, /data-action="confirm-config-backup-restore"/);
  assert.match(markup, /data-backup-id="backup-1"/);
});
