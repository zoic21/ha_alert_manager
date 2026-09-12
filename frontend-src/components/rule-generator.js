import { renderConfigurationDrawer } from "./configuration-drawer.js";
import { esc } from "../utils/escaping.js";

export function renderRuleGenerator({ drawer, busy, useBottomSheet, t }) {
  // Available groups precede unavailable groups, including across categories.
  const groups = new Map();
  for (const row of drawer.rows) {
    const group = `${["available", "already_generated"].includes(row.status) ? "available" : "unavailable"}:${row.category}`;
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push(row);
  }
  const content = drawer.loading ? `<p role="status">${esc(t("loading"))}</p>`
    : [...groups.values()].map((rows) => `<section class="generator-category">
        <h3>${esc(t(`generator.categories.${rows[0].category}`))}</h3>
        ${rows.map((row) => `<div class="generator-row">
          <ha-checkbox data-blueprint-id="${esc(row.blueprint_id)}" aria-label="${esc(t(row.name_key))}" ${!["available", "already_generated"].includes(row.status) || busy ? "disabled" : ""}></ha-checkbox>
          <div><strong>${esc(t(row.name_key))}</strong><p>${esc(t(row.description_key))}</p>
            <small>${esc(t("generator.entity_count", { count: row.entity_count }))}${row.status === "available" ? "" : ` · ${esc(t(`generator.status.${row.status}`))}`}${row.replaced_by ? ` · ${esc(t("generator.replacement", { id: row.replaced_by }))}` : ""}</small>
          </div>
        </div>`).join("")}
      </section>`).join("");
  return renderConfigurationDrawer({
    title: t("generator.title"), ariaLabel: t("generator.title"),
    resizeLabel: t("rules.aria_resize"),
    headerAction: `<ha-button slot="actionItems" data-action="refresh-rule-generator" ${busy || drawer.loading ? "disabled" : ""}>${esc(t("generator.refresh"))}</ha-button>`,
    banner: `<ha-alert alert-type="info">${esc(t("generator.help"))}</ha-alert>`,
    content, saveAction: "generate-rules", saveLabel: t("generator.create"),
    busy: busy || drawer.loading || !drawer.selected.size, useBottomSheet,
  });
}

export function hydrateRuleGenerator(root, panel) {
  const drawer = panel._configurationDrawer;
  if (drawer?.kind !== "generator") return;
  root?.querySelectorAll?.("ha-checkbox[data-blueprint-id]").forEach((checkbox) => {
    checkbox.checked = drawer.selected.has(checkbox.dataset.blueprintId);
    // Property assignment keeps repeated hydration idempotent.
    checkbox.onchange = () => {
      if (checkbox.disabled || panel._busy) return;
      const id = checkbox.dataset.blueprintId;
      if (checkbox.checked) drawer.selected.add(id);
      else drawer.selected.delete(id);
      const create = root.querySelector('[data-action="generate-rules"]');
      if (create) create.disabled = !drawer.selected.size || panel._busy;
    };
  });
}

export async function handleRuleGeneratorAction(panel, action) {
  if (action === "open-rule-generator") {
    if (panel._busy) return true;
    if (panel._ruleDirty && !window.confirm(panel._t("rules.discard_confirm"))) return true;
    panel._editingRule = null;
    panel._ruleDirty = false;
    panel._configurationDrawer = { kind: "generator", rows: [], selected: new Set(), loading: false };
    action = "refresh-rule-generator";
  }
  const drawer = panel._configurationDrawer;
  if (drawer?.kind !== "generator") return false;
  if (action === "close-configuration-drawer") {
    if (panel._busy) return true;
    panel._configurationDrawer = null;
    panel._render();
    return true;
  }
  if (action === "refresh-rule-generator") {
    if (panel._busy || drawer.loading) return true;
    drawer.loading = true;
    drawer.selected.clear();
    panel._render();
    const rows = await panel._call({ type: "alert_manager/rules/blueprints/list" });
    if (panel._configurationDrawer !== drawer) return true;
    drawer.rows = rows ?? [];
    drawer.loading = false;
    panel._render();
    return true;
  }
  if (action === "generate-rules") {
    if (panel._busy || drawer.loading || !drawer.selected.size) return true;
    const overwrite = drawer.rows.some((row) => drawer.selected.has(row.blueprint_id)
      && row.status === "already_generated");
    if (overwrite && !window.confirm(panel._t("generator.overwrite_confirm"))) return true;
    const result = await panel._call({
      type: "alert_manager/rules/blueprints/create", blueprint_ids: [...drawer.selected],
      ...(overwrite ? { overwrite: true } : {}),
    }, panel._t("generator.created"));
    if (result) {
      for (const rule of result) {
        const index = panel._config.rules.findIndex((existing) => existing.id === rule.id);
        if (index < 0) panel._config.rules.push(rule);
        else panel._config.rules[index] = rule;
      }
      if (panel._configurationDrawer === drawer) {
        panel._configurationDrawer = null;
        panel._notice = { kind: "success", text: panel._t("generator.created") };
      }
    }
    panel._render();
    return true;
  }
  return false;
}

export function refreshRuleGeneratorState(panel) {
  const drawer = panel._configurationDrawer;
  if (drawer?.kind !== "generator") return;
  for (const action of ["generate-rules", "refresh-rule-generator"]) {
    const button = panel.shadowRoot?.querySelector?.(`[data-action="${action}"]`);
    if (button) button.disabled = panel._busy || drawer.loading
      || (action === "generate-rules" && !drawer.selected.size);
  }
}
