import { automaticConfig, automaticPacks } from "./automatic-fixtures.mjs";
import { automaticPackToDraft } from "../frontend-src/components/configuration-yaml.js";
import assert from "node:assert/strict";
import test from "node:test";

import { handleAutomaticAction, renderAutomatic } from "../frontend-src/views/automatic.js";
import {
  renderBackupRestoreDialog, renderConfigBackups,
} from "../frontend-src/components/config-backups.js";
import {
  mountConfigurationDrawer, renderConfigurationDrawer, renderConfigurationRemove,
  replaceConfigurationDrawer, revealAddedRow,
} from "../frontend-src/components/configuration-drawer.js";
import { MDI_CLOSE } from "../frontend-src/utils/constants.js";
import {
  renderCoherence, renderDeletedEntitiesDrawer,
} from "../frontend-src/views/coherence.js";
import { renderHistory } from "../frontend-src/views/history.js";
import {
  renderOverview, startupBannerMarkup, startupStatusText,
} from "../frontend-src/views/overview.js";
import {
  handleSettingsAction,
  renderSettings,
  renderRuntimeStatistics,
  formatStatisticsTime,
  refreshNotificationProfileUsage,
} from "../frontend-src/views/settings.js";

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

test("overview startup banner follows the transactional runtime phase", () => {
  const startup = {
    in_progress: true,
    stabilization_until: "2026-09-04T10:02:00+00:00",
  };
  const now = Date.parse("2026-09-04T10:00:01+00:00");
  const translate = (key, replacements = {}) => (
    `${key}:${replacements.duration ?? ""}`
  );

  assert.equal(
    startupStatusText(startup, translate, (seconds) => `${seconds} s`, now),
    "overview.startup_in_progress:119 s",
  );
  assert.match(
    startupBannerMarkup(startup, translate, (seconds) => `${seconds} s`, now),
    /<ha-alert[^>]*alert-type="info"[^>]*role="status"/,
  );
  assert.equal(
    startupStatusText(startup, translate, String, Date.parse(startup.stabilization_until)),
    "overview.startup_waiting:",
  );
  assert.equal(startupBannerMarkup({ in_progress: false }, translate, String, now), "");
});

test("overview hides the provisional tracked total during startup", () => {
  const markup = renderOverview({
    alerts: {
      active_count: 0,
      pending_count: 0,
      acknowledge_count: 0,
      tracked_count: 3,
      startup: { in_progress: true, stabilization_until: null },
    },
    selectedStatuses: [],
    pageMessages: "",
    durationText: String,
    rows: [],
    renderAlertTable: (_kind, _rows, header) => header,
    t,
  });

  assert.match(markup, /data-summary="tracked"[\s\S]*<strong class="summary-calculating" title="overview\.summary_tracked_calculating">overview\.summary_tracked_calculating<\/strong>/);
  assert.doesNotMatch(markup, /data-summary="tracked"[\s\S]*<strong>3<\/strong>/);
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
  assert.match(enabled, /^history:row-1:<messages><\/messages>/);
  assert.match(enabled, /class="panel history-panel"/);
  assert.match(enabled, /history\.title/);
  assert.match(enabled, /data-action="clear-history"/);
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

test("updating a mobile configuration drawer preserves its native bottom sheet", () => {
  const revealed = [];
  const nextScroller = {
    scrollTop: 0,
    querySelector: (selector) => ({
      scrollIntoView: (options) => revealed.push({ selector, options }),
    }),
  };
  const nextDrawer = {
    querySelector: (selector) => (
      selector === ".side-drawer-form" ? nextScroller : null
    ),
  };
  const nextBottomSheet = {
    querySelector: (selector) => (
      selector === ".configuration-drawer" ? nextDrawer : null
    ),
  };
  const template = {
    content: {
      querySelector: (selector) => (
        selector === ".side-drawer-bottom-sheet" ? nextBottomSheet : null
      ),
    },
    set innerHTML(value) { this.markup = value; },
  };
  const originalDocument = globalThis.document;
  const originalRequestAnimationFrame = globalThis.requestAnimationFrame;
  const animationFrames = [];
  globalThis.document = {
    createElement: (tagName) => {
      assert.equal(tagName, "template");
      return template;
    },
  };
  globalThis.requestAnimationFrame = (callback) => {
    animationFrames.push(callback);
  };
  let replacement;
  let bottomSheetRemoved = false;
  let fallbackInserted = false;
  const currentScroller = { scrollTop: 246 };
  const currentDrawer = {
    querySelector: (selector) => (
      selector === ".side-drawer-form" ? currentScroller : null
    ),
    replaceWith: (node) => { replacement = node; },
  };
  const currentBottomSheet = {
    querySelector: (selector) => (
      selector === ".configuration-drawer" ? currentDrawer : null
    ),
    remove: () => { bottomSheetRemoved = true; },
  };
  const root = {
    querySelector: (selector) => (
      selector === ".side-drawer-bottom-sheet" ? currentBottomSheet : null
    ),
    insertAdjacentHTML: () => { fallbackInserted = true; },
  };

  try {
    replaceConfigurationDrawer(
      root,
      '<ha-resizable-bottom-sheet class="side-drawer-bottom-sheet"><ha-card class="configuration-drawer"></ha-card></ha-resizable-bottom-sheet>',
    );
    nextScroller.scrollTop = 0;
    animationFrames.shift()();
    assert.equal(nextScroller.scrollTop, 246);
    nextScroller.scrollTop = 0;
    animationFrames.shift()();
    assert.deepEqual(revealed, []);
    replaceConfigurationDrawer(root, template.markup, '[data-notification-exception="1"]');
    assert.deepEqual(revealed, []);
    animationFrames.shift()();
    assert.deepEqual(revealed, []);
    animationFrames.shift()();
    assert.deepEqual(revealed, []);
    animationFrames.shift()();
    assert.deepEqual(revealed, [{
      selector: '[data-notification-exception="1"]', options: { block: "nearest" },
    }]);
  } finally {
    globalThis.document = originalDocument;
    globalThis.requestAnimationFrame = originalRequestAnimationFrame;
  }

  assert.equal(replacement, nextDrawer);
  assert.equal(bottomSheetRemoved, false);
  assert.equal(fallbackInserted, false);
  assert.equal(nextScroller.scrollTop, 246);
  assert.match(template.markup, /^<ha-resizable-bottom-sheet/);
});

test("automatic rendering is pure and places defaults with sparse exceptions", () => {
  const config = { automatic: automaticConfig() };
  config.automatic.battery.device_overrides = { "device-1": { threshold: 15 } };
  const packs = automaticPacks();
  const context = { availablePacks: packs, config, draft: Object.fromEntries(packs.map((pack) => [pack.id, automaticPackToDraft(pack, config.automatic[pack.id])])), configurationDrawer: { kind: "automatic", id: "battery" }, t };
  const before = structuredClone(context.draft);
  const markup = renderAutomatic(context);
  assert.deepEqual(context.draft, before);
  assert.match(markup, /^<ha-card id="settings-section-automatic" outlined/);
  assert.match(markup, /auto-battery-enabled[^>]*checked/);
  assert.match(markup, /auto-battery-delay/);
  assert.match(markup, /auto-battery-threshold/);
  assert.match(markup, /auto-battery-device_overrides-target-0/);
  assert.ok(markup.indexOf("</form>") < markup.indexOf('class="side-drawer configuration-drawer"'));
  assert.match(markup, /data-action="remove-pack-map-row"/);
  assert.doesNotMatch(markup, /data-action="inherit-pack-row"/);
  assert.doesNotMatch(markup, /automatic.inherited_value/);
});

test("flapping source contexts share one drawer without an ordinary delay", () => {
  const packs = automaticPacks(); const config = { automatic: automaticConfig() };
  config.automatic.flapping.source_packs.unavailable.entity_overrides = { "sensor.a": { recovery: 30 } };
  const draft = Object.fromEntries(packs.map((pack) => [pack.id, automaticPackToDraft(pack, config.automatic[pack.id])]));
  const markup = renderAutomatic({ availablePacks: packs, config, draft, configurationDrawer: { kind: "automatic", id: "flapping", sourceId: "unavailable" }, t });
  assert.equal((markup.match(/class="side-drawer configuration-drawer"/g) ?? []).length, 1);
  assert.match(markup, /auto-flapping-source-context/);
  assert.match(markup, /class="field full switch-field-row"><span[^>]*>[^<]*<\/span><ha-switch id="auto-flapping-source-enabled"/);
  assert.match(markup, /auto-flapping-entity_overrides-target-0/);
  assert.doesNotMatch(markup, /id="auto-flapping-delay"/);
});

test("settings rendering consumes prepared drafts without initializing them", () => {
  const automaticMarkup = "<section id=\"settings-section-automatic\">automatic</section>";
  const markup = renderSettings({
    config: { global_delay: 900, pending_display_delay: 10 },
    settingsDraft: {
      coherence_scan_esphome: true,
      coherence_alert_enabled: true,
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
    configurationDirty: true,
    busy: false,
    automaticMarkup,
    renderNumberField: (id, label, value) => `<number id="${id}">${label}:${value}</number>`,
    t,
  });

  assert.doesNotMatch(markup, /id="global-delay"/);
  assert.match(markup, /class="panel settings-navigation"/);
  assert.equal(markup.match(/data-action="scroll-settings-section"/g)?.length, 7);
  assert.equal(markup.match(/appearance="outlined" data-action="scroll-settings-section"/g)?.length, 7);
  assert.equal(markup.match(/<ha-icon slot="start" icon="mdi:/g)?.length, 7);
  assert.match(markup, /data-section-id="miscellaneous"/);
  assert.doesNotMatch(markup, /data-section-id="(?:alert-display|history)"/);
  const miscellaneousCard = markup.match(/<ha-card id="settings-section-miscellaneous"[\s\S]*?<\/ha-card>/)[0];
  assert.match(miscellaneousCard, /class="settings-grid"/);
  assert.match(miscellaneousCard, /id="pending-display-delay"/);
  assert.match(miscellaneousCard, /id="history-limit"/);
  assert.match(markup, /data-section-id="automatic"><ha-icon slot="start" icon="mdi:radar"/);
  assert.match(markup, /data-section-id="transfer"><ha-icon slot="start" icon="mdi:file-swap-outline"/);
  assert.ok(markup.includes(automaticMarkup));
  assert.ok(markup.indexOf(automaticMarkup) < markup.indexOf("settings-section-miscellaneous"));
  assert.match(markup, /id="settings-section-notifications"/);
  assert.match(markup, /coherence-scan-esphome[^>]*checked/);
  const coherenceCard = markup.match(/<ha-card id="settings-section-coherence"[\s\S]*?<\/ha-card>/)[0];
  assert.match(coherenceCard, /class="coherence-options"/);
  assert.match(coherenceCard, /id="coherence-alert-enabled"[^>]*checked/);
  assert.match(coherenceCard, /aria-describedby="coherence-alert-help"/);
  assert.match(markup, /data-ignored-reference="sensor.old"/);
  assert.match(markup, /value="sensor.new"/);
  assert.doesNotMatch(markup, /settings-entity_delays-configuration/);
  assert.match(markup, /class="side-drawer configuration-drawer"/);
  assert.match(markup, new RegExp(`ha-icon-button[^>]*path="${MDI_CLOSE}"`));
  assert.match(markup, /configuration-section-heading[\s\S]*data-action="add-entity-delay"[\s\S]*class="delay-list"/);
  assert.match(markup, /data-duration-value="60"[^>]*data-delay-index="0"/);
  assert.ok(markup.indexOf("</form>") < markup.indexOf('class="side-drawer configuration-drawer"'));
  assert.match(markup, /slot="fab" size="l" class="dirty"[^>]*data-action="save-configuration"/);
});

test("settings quick access scrolls smoothly to automatic monitoring", async () => {
  let scrollOptions;
  const section = {
    scrollIntoView: (options) => { scrollOptions = options; },
  };
  const panel = {
    shadowRoot: {
      querySelector: (selector) => (
        selector === "#settings-section-automatic" ? section : null
      ),
    },
  };

  const handled = await handleSettingsAction.call(
    panel,
    "scroll-settings-section",
    { dataset: { sectionId: "automatic" } },
  );

  assert.equal(handled, true);
  assert.deepEqual(scrollOptions, { behavior: "smooth", block: "start" });
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
      coherence_alert_enabled: true,
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

  assert.match(markup, /^<ha-dialog[^>]+type="alert"[^>]+width="small"/);
  assert.match(markup, /header-title="recovery\.confirm_title"/);
  assert.match(markup, /aria-describedby="config-backup-confirmation"/);
  assert.doesNotMatch(markup, /<ha-dialog-header>/);
  assert.match(markup, /<ha-dialog-footer slot="footer">/);
  assert.match(markup, /slot="secondaryAction"[^>]+data-action="cancel-config-backup-restore"/);
  assert.match(markup, /slot="primaryAction"[^>]+data-action="confirm-config-backup-restore"/);
  assert.match(markup, /data-backup-id="backup-1"/);
});


test("all configuration drawers keep save actions outside their scroll area", () => {
  for (const useBottomSheet of [false, true]) {
    const markup = renderConfigurationDrawer({
      title: "Configuration", ariaLabel: "Configuration", resizeLabel: "Resize drawer", content: "Long content",
      saveAction: "save-settings", saveLabel: "Save", busy: false, useBottomSheet,
    });
    assert.match(markup, /role="separator" aria-orientation="vertical" aria-label="Resize drawer" tabindex="0"/);
    assert.match(markup, /<section class="side-drawer-section"><div data-active-notice><\/div>Long content<\/section>\s*<\/div>\s*<div class="actions side-drawer-actions">/);
  }
});


test("configuration overlays mount outside the tabs page on mobile and desktop", () => {
  for (const mobile of [false, true]) {
    const page = {};
    const sheet = mobile ? { parentNode: page } : null;
    const backdrop = mobile ? null : { parentNode: page };
    const drawer = { parentNode: sheet ?? page, closest: () => sheet };
    const appended = [];
    const root = {
      querySelector: (selector) => selector === ".configuration-drawer" ? drawer : backdrop,
      append: (node) => { node.parentNode = root; appended.push(node); },
    };
    mountConfigurationDrawer(root);
    assert.deepEqual(appended, mobile ? [sheet] : [backdrop, drawer]);
    assert.equal((sheet ?? drawer).parentNode, root);
    mountConfigurationDrawer(root);
    assert.equal(appended.length, mobile ? 1 : 2);
  }
});


test("a newly opened configuration drawer can be inserted into the panel shadow root", () => {
  const originalDocument = globalThis.document;
  const fragment = {};
  const template = { content: fragment, innerHTML: "" };
  const appended = [];
  // ShadowRoot supports append, but has no insertAdjacentHTML method.
  const toggles = [];
  const root = {
    querySelector: (selector) => selector === ".settings-page"
      ? { classList: { toggle: (...args) => toggles.push(args) } } : null,
    append: (node) => appended.push(node),
  };
  globalThis.document = { createElement: () => template };
  try {
    replaceConfigurationDrawer(root, '<ha-card class="configuration-drawer"></ha-card>');
    assert.deepEqual(appended, [fragment]);
    assert.deepEqual(toggles, [["has-editor", true]]);
    assert.match(template.innerHTML, /configuration-drawer/);
  } finally {
    globalThis.document = originalDocument;
  }
});


test("configuration row removal uses an accessible shared trash icon", () => {
  const markup = renderConfigurationRemove('Retirer "ceci"', "remove-entity-delay", { "data-index": 2 });
  assert.match(markup, /<ha-icon-button class="configuration-remove" data-action="remove-entity-delay" data-index="2"/);
  assert.match(markup, /aria-label="Retirer &quot;ceci&quot;" title="Retirer &quot;ceci&quot;"/);
  assert.match(markup, /<ha-icon icon="mdi:delete-outline"><\/ha-icon>/);
  assert.doesNotMatch(markup, /<ha-button/);
});


test("added rows reveal after rendering and ignore rows removed before the frame", () => {
  const originalRequestAnimationFrame = globalThis.requestAnimationFrame;
  const frames = [];
  const calls = [];
  const row = { isConnected: true, scrollIntoView: options => calls.push(options) };
  const root = { querySelector: selector => selector === ".new-row" ? row : null };
  globalThis.requestAnimationFrame = callback => frames.push(callback);
  try {
    revealAddedRow(root, ".new-row");
    assert.deepEqual(calls, []);
    frames.shift()();
    assert.deepEqual(calls, [{ block: "nearest" }]);
    revealAddedRow(root, ".new-row");
    row.isConnected = false;
    frames.shift()();
    assert.equal(calls.length, 1);
    revealAddedRow(root, ".missing");
    revealAddedRow(root);
    assert.equal(frames.length, 0);
  } finally {
    globalThis.requestAnimationFrame = originalRequestAnimationFrame;
  }
});


for (const [packId, fieldId, fieldType] of [
  ["battery", "device_overrides", "device_settings_map"],
  ["execution_errors", "entity_overrides", "entity_settings_map"],
  ["flapping", "entity_overrides", "entity_settings_map"],
]) {
  test(`${packId} adding a configuration reveals the newly appended row`, async () => {
    const rows = [{ target_id: "existing", value: 4 }];
    const calls = [];
    const addedRow = { scrollIntoView: options => calls.push(options) };
    const drawer = { querySelector: selector => {
      assert.equal(selector, ".automatic-exception:last-child");
      assert.equal(rows.length, 2);
      return addedRow;
    } };
    const panel = {
      _packs: [{ id: packId, config_fields: [{ id: fieldId, type: fieldType, fields: [] }] }],
      _automaticMapDraft: { [packId]: { [fieldId]: rows } },
      _ensureAutomaticDraft() {},
      _markConfigurationDirty() {},
      _render() {},
      shadowRoot: {
        querySelector: selector => selector === ".configuration-drawer" ? drawer : null,
        querySelectorAll: () => [],
      },
    };
    await handleAutomaticAction.call(panel, "add-pack-map-row", {
      dataset: { packId, fieldId },
    });
    assert.equal(rows[0].target_id, "existing");
    assert.equal(rows[1].target_id, "");
    assert.deepEqual(calls, [{ block: "nearest" }]);
  });
}


test("targeted configuration drawer replacement releases the main page on close", () => {
  const toggles = [];
  const root = {
    querySelector: (selector) => selector === ".settings-page"
      ? { classList: { toggle: (...args) => toggles.push(args) } } : null,
  };
  replaceConfigurationDrawer(root, "");
  assert.deepEqual(toggles, [["has-editor", false]]);
});


test("runtime diagnostics render scope, period and aggregates with escaped values", () => {
  const markup = renderRuntimeStatistics({
    statistics: {
      evaluation_count: 4, evaluation_average_ms: 0.5,
      evaluation_max_ms: 2, evaluation_total_ms: 2000,
      pending: 1, activations: 2, acknowledgments: 3, resolutions: 4,
      notifications: 5, observed_from: "<start>", observed_until: "<end>",
    },
    date: (value) => value,
    t: (key, values) => values ? `${key}: ${values.start} / ${values.end}` : key,
  });
  assert.equal(markup.match(/<dt>/g).length, 9);
  assert.match(markup, /statistics.scope/);
  assert.match(markup, /statistics.window/);
  assert.match(markup, /&lt;start&gt; \/ &lt;end&gt;/);
  assert.match(markup, /500.00 µs/);
  assert.match(markup, /2.00 ms/);
  assert.match(markup, /2.00 s/);
  assert.equal(formatStatisticsTime(0), "0 ms");
  assert.equal(formatStatisticsTime(1000), "1.00 s");
});

test("statistics refresh replaces only the diagnostic content and profile counts", () => {
  const diagnostic = {};
  const profile = { dataset: { notificationProfileUsage: "phone" } };
  refreshNotificationProfileUsage.call({
    shadowRoot: {
      querySelector: (selector) => selector === "#settings-section-diagnostics" ? diagnostic : null,
      querySelectorAll: () => [profile],
    },
    _notificationStats: {
      last_24h: { phone: 1 },
      diagnostics: { evaluation_count: 42, observed_from: "start", observed_until: "end" },
    },
    _date: (value) => value,
    _t: t,
  });
  assert.match(diagnostic.innerHTML, /<dd>42<\/dd>/);
  assert.equal(profile.textContent, "notifications.usage_last_24h_one");
});

test("history statistics replace the table only when explicitly opened", () => {
  const context = { busy: false, limit: 100, rows: [], pageMessages: "", t, renderAlertTable: () => "history-table" };
  assert.equal(renderHistory(context), "history-table");
  const markup = renderHistory({ ...context, statisticsOpen: true });
  assert.match(markup, /data-history-statistics-page/);
  assert.match(markup, /history-statistics-period/);
  assert.match(markup, /data-history-statistics-leaders/);
  assert.match(markup, /data-history-statistics-summary/);
  assert.doesNotMatch(markup, /hass-tabs-subpage-data-table|slot="top-header"|history-statistics-group/);
  assert.doesNotMatch(markup, /history.statistics.help|history-statistics-help|history-statistics-note|history-statistics-drilldown/);
  assert.doesNotMatch(renderHistory({ ...context, statisticsOpen: true, limit: 0 }), /data-history-statistics-page/);
});

test("coherence report keeps settings out of its header before and after a scan", () => {
  for (const result of [null, { results: [] }]) {
    const markup = renderCoherence({
      result, loading: false, pageMessages: "", statsMarkup: "", t,
    });
    assert.doesNotMatch(markup, /coherence-alert-enabled|coherence.alert_help/);
    assert.match(markup, /data-action="scan-coherence"/);
  }
});

for (const id of ["unavailable", "connectivity", "unifi", "battery", "execution_errors", "flapping"]) {
  test(`compact ${id} configuration groups defaults and exception fields without a duplicate switch`, () => {
    const packs = automaticPacks();
    const config = { automatic: automaticConfig() };
    config.automatic[id].device_overrides = { device: {} };
    config.automatic[id].entity_overrides = { "sensor.example": {} };
    const draft = Object.fromEntries(packs.map((pack) => [pack.id, automaticPackToDraft(pack, config.automatic[pack.id])]));
    const markup = renderAutomatic({ availablePacks: packs, config, draft, configurationDrawer: { kind: "automatic", id }, t });
    assert.doesNotMatch(markup, /drawer-enabled/);
    assert.match(markup, new RegExp(`id="auto-${id}-enabled"`));
    assert.match(markup, /class="automatic-pack-settings"/);
    const row = markup.slice(markup.indexOf(`id="auto-${id}-entity_overrides-target-0"`));
    const monitoring = row.slice(row.indexOf('class="field pack-setting-field pack-monitoring-field"'), row.indexOf('</div>', row.indexOf('class="field pack-setting-field pack-monitoring-field"')));
    assert.match(monitoring, new RegExp(`entity_overrides-0-enabled`));
    assert.doesNotMatch(monitoring, /<small>/);
    assert.doesNotMatch(row, /automatic.inherited_value/);
    assert.match(monitoring, /<ha-switch[^>]*checked/);
    if (id === "execution_errors") {
      assert.doesNotMatch(markup, /data-field-id="device_overrides"/);
      assert.match(markup, /auto-execution_errors-delay[\s\S]*auto-execution_errors-failure_threshold/);
    } else assert.match(markup, new RegExp(`auto-${id}-device_overrides-target-0`));
  });
}

test("flapping respects the selected source's exception targets without losing saved data", () => {
  const packs = automaticPacks();
  const config = { automatic: automaticConfig() };
  config.automatic.flapping.source_packs.execution_errors = {
    device_overrides: { old_device: { occurrences: 9 } },
    entity_overrides: { "automation.test": { occurrences: 3 } },
  };
  const draft = Object.fromEntries(packs.map((pack) => [pack.id, automaticPackToDraft(pack, config.automatic[pack.id])]));
  const before = structuredClone(draft);
  const markup = renderAutomatic({ availablePacks: packs, config, draft, configurationDrawer: { kind: "automatic", id: "flapping", sourceId: "execution_errors" }, t });
  assert.doesNotMatch(markup, /data-field-id="device_overrides"/);
  assert.match(markup, /auto-flapping-entity_overrides-target-0/);
  assert.deepEqual(draft, before);
});


test("disabled device blocks entity switches and retains greyed settings until reenabled", () => {
  const packs = automaticPacks();
  const config = { automatic: automaticConfig() };
  config.automatic.battery.device_overrides = { dev: { enabled: false } };
  config.automatic.battery.entity_overrides = { "sensor.a": { enabled: true, delay: 42, threshold: 12 } };
  const draft = Object.fromEntries(packs.map((pack) => [pack.id, automaticPackToDraft(pack, config.automatic[pack.id])]));
  const context = { availablePacks: packs, config, draft, configurationDrawer: { kind: "automatic", id: "battery" }, hass: { entities: { "sensor.a": { device_id: "dev" } }, devices: { dev: {} } }, t };
  let markup = renderAutomatic(context);
  assert.match(markup, /automatic.blocked_device/);
  assert.match(markup, /id="auto-battery-entity_overrides-0-enabled"[^>]*disabled=""[^>]*checked/);
  assert.match(markup, /id="auto-battery-entity_overrides-0-delay"[^>]*data-duration-value="42"[^>]*disabled=""/);
  draft.battery.device_overrides[0].enabled = true;
  markup = renderAutomatic(context);
  assert.doesNotMatch(markup, /automatic.blocked_device/);
  assert.doesNotMatch(markup.match(/id="auto-battery-entity_overrides-0-enabled"[^>]*>/)[0], /disabled/);
  draft.battery.entity_overrides[0].enabled = false;
  markup = renderAutomatic(context);
  assert.doesNotMatch(markup.match(/id="auto-battery-entity_overrides-0-enabled"[^>]*>/)[0], /checked|disabled/);
  assert.match(markup, /id="auto-battery-entity_overrides-0-delay"[^>]*data-duration-value="42"[^>]*disabled=""/);
  assert.equal(draft.battery.entity_overrides[0].threshold, 12);
});
