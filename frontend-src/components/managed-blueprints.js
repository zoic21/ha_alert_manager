import { rememberManagedBlueprints } from "../api/alert-manager-api.js";
import { esc } from "../utils/escaping.js";

function comparableBlueprintValue(rule, key, value) {
  if (key !== "value" || !["above", "below", "between", "outside"].includes(rule.operator)) return value;
  // The visual editor stores thresholds as strings; recipes may use numbers.
  // Preserve empty/invalid values and range order so real changes stay visible.
  return (Array.isArray(value) ? value : [value]).map((item) => {
    if (typeof item !== "number" && (typeof item !== "string" || !item.trim())) return item;
    const number = Number(item);
    return Number.isFinite(number) ? number : item;
  });
}

export function renderManagedBlueprint({ rule, proposal, review, t }) {
  if (!rule?.blueprint?.managed) return "";
  const notice = proposal?.update_available
    ? `<ha-alert alert-type="info">${esc(t("managed.summary", { added: proposal.added.length, removed: proposal.removed.length }))}${proposal.version_available ? ` · ${esc(t("managed.version"))}` : ""}</ha-alert>` : "";
  const choices = review ? [...new Set([
    ...review.proposal.discovered, ...rule.entity_ids,
  ])].sort() : [];
  const missingExclusions = review ? (rule.blueprint.excluded_entities ?? []).filter((id) => !choices.includes(id)) : [];
  const changes = review ? Object.entries(review.proposal.candidate).filter(([key, value]) => (
    !["id", "blueprint", "entity_ids", "version"].includes(key)
    && JSON.stringify(comparableBlueprintValue(review.proposal.candidate, key, value))
      !== JSON.stringify(comparableBlueprintValue(rule, key, rule[key]))
  )) : [];
  return `<section class="rule-editor-section">
    <strong>${esc(t("managed.source", { id: rule.blueprint.id, version: rule.blueprint.version }))}</strong>
    <p>${esc(t("managed.help"))}</p>${notice}${proposal?.invalid ? `<ha-alert alert-type="warning">${esc(t("managed.invalid"))}</ha-alert>` : ""}
    <div class="managed-actions"><ha-button data-action="review-blueprint"><ha-icon slot="start" icon="mdi:refresh"></ha-icon>${esc(t("managed.review"))}</ha-button>
    <ha-button data-action="detach-blueprint"><ha-icon slot="start" icon="mdi:link-off"></ha-icon>${esc(t("managed.detach"))}</ha-button></div>
    ${review ? `<div class="managed-review"><h3>${esc(t("managed.review"))}</h3><p>${esc(t("managed.selection_help"))}</p>
      ${choices.map((id) => `<div class="managed-entity"><ha-checkbox data-managed-entity="${esc(id)}" aria-label="${esc(id)}"></ha-checkbox><span><strong data-managed-membership="${esc(id)}">${esc(t(review.selected?.has(id) ? "managed.monitored" : "managed.excluded"))}</strong> · ${esc(id)}${review.proposal.added.includes(id) ? ` · ${esc(t("managed.added"))}` : review.proposal.removed.includes(id) ? ` · ${esc(t("managed.removed"))}` : ""}</span></div>`).join("")}
      ${missingExclusions.length ? `<p>${esc(t("managed.keep_exclusions"))}</p>${missingExclusions.map((id) => `<div class="managed-entity"><ha-checkbox data-managed-exclusion="${esc(id)}" aria-label="${esc(id)}"></ha-checkbox><span>${esc(id)}</span></div>`).join("")}` : ""}
      ${changes.length ? `<h4>${esc(t("managed.changes"))}</h4><dl>${changes.map(([key, value]) => `<dt>${esc(key)}</dt><dd>${esc(JSON.stringify(rule[key]))} → ${esc(JSON.stringify(value))}</dd>`).join("")}</dl>` : ""}
      <div class="managed-actions"><ha-button data-action="apply-blueprint"><ha-icon slot="start" icon="mdi:check"></ha-icon>${esc(t("managed.apply"))}</ha-button></div>
    </div>` : ""}
  </section>`;
}

export function hydrateManagedBlueprint(panel) {
  const review = panel._blueprintReview;
  panel.shadowRoot?.querySelectorAll?.("[data-managed-exclusion]").forEach((checkbox) => {
    checkbox.checked = review?.keptExclusions.has(checkbox.dataset.managedExclusion) ?? false;
    checkbox.disabled = panel._busy;
    checkbox.onchange = () => {
      if (!review || panel._busy) return;
      if (checkbox.checked) review.keptExclusions.add(checkbox.dataset.managedExclusion);
      else review.keptExclusions.delete(checkbox.dataset.managedExclusion);
    };
  });
  panel.shadowRoot?.querySelectorAll?.("[data-managed-entity]").forEach((checkbox) => {
    checkbox.checked = review?.selected.has(checkbox.dataset.managedEntity) ?? false;
    checkbox.disabled = panel._busy;
    checkbox.onchange = () => {
      if (!review || panel._busy) return;
      if (checkbox.checked) review.selected.add(checkbox.dataset.managedEntity);
      else review.selected.delete(checkbox.dataset.managedEntity);
      const label = checkbox.parentElement?.querySelector("[data-managed-membership]");
      if (label) label.textContent = panel._t(checkbox.checked ? "managed.monitored" : "managed.excluded");
      panel._clearRuleEditorError?.();
    };
  });
}

export async function handleManagedBlueprintAction(panel, action) {
  if (!["review-blueprint", "apply-blueprint", "detach-blueprint"].includes(action)) return false;
  const rule = panel._editingRule;
  if (!rule?.blueprint?.managed || panel._busy) return true;
  if (panel._ruleDirty) {
    panel._ruleEditorError = panel._t("managed.save_first");
    panel._refreshRuleEditor();
    return true;
  }
  if (action === "review-blueprint") {
    let proposal = panel._managedBlueprints?.[rule.id];
    if (!proposal || Date.now() - proposal.checkedAt >= 15000
      || proposal.ruleSignature !== JSON.stringify(rule)) {
      const rows = await panel._call({ type: "alert_manager/rules/blueprints/reconcile" });
      if (panel._editingRule !== rule || panel.isConnected === false || panel._ruleDirty) return true;
      if (rows) rememberManagedBlueprints(panel, rows);
      proposal = rows?.find((row) => row.rule_id === rule.id);
    }
    if (proposal) {
      panel._blueprintReview = { proposal, selected: new Set(proposal.candidate.entity_ids), keptExclusions: new Set(rule.blueprint.excluded_entities ?? []) };
      panel._refreshRulesData();
      panel._refreshRuleEditor();
    }
    return true;
  }
  let message;
  if (action === "detach-blueprint") {
    if (!window.confirm(panel._t("managed.detach_confirm"))) return true;
    message = { type: "alert_manager/rules/blueprints/detach", rule_id: rule.id };
  } else {
    const review = panel._blueprintReview;
    if (!review || review.proposal.rule_id !== rule.id) return true;
    if (!review.selected.size) {
      panel._ruleEditorError = panel._t("managed.empty");
      panel._refreshRuleEditor();
      return true;
    }
    const excluded = [...new Set([
      ...review.keptExclusions, ...review.proposal.discovered,
      ...rule.entity_ids,
    ])].filter((id) => !review.selected.has(id));
    message = {
      type: "alert_manager/rules/blueprints/apply", rule_id: rule.id,
      token: review.proposal.token, entity_ids: [...review.selected].sort(),
      excluded_entities: excluded.sort(),
    };
  }
  const updated = await panel._call(message, panel._t("success.rule_updated"));
  if (panel._editingRule !== rule || panel.isConnected === false) {
    if (updated) panel._replaceRule(updated);
    return true;
  }
  if (updated) {
    panel._blueprintReview = null;
    panel._replaceRule(updated);
    panel._editingRule = updated;
    panel._refreshRuleEditor();
    panel._refreshTabData("rules");
  } else {
    panel._ruleEditorError = panel._notice?.text || panel._t("errors.unknown");
    panel._notice = null;
    panel._refreshRuleEditor();
  }
  return true;
}
