import { MDI_CLOSE } from "../utils/constants.js";
import { esc } from "../utils/escaping.js";

export function renderEntityReplacement({ state, t }) {
  if (!state) return "";
  const preview = state.preview;
  const correction = state.coherenceCorrection;
  const selected = state.selected?.size ?? 0;
  const content = state.result
    ? `<ha-alert alert-type="success">${esc(t("coherence.replacement.success", state.result))}</ha-alert>
       <p>${esc(t(state.result.yaml_changed ? "coherence.replacement.reload" : "coherence.replacement.dashboard_saved"))}</p>`
    : preview
      ? `${correction ? `<p>${esc(t("coherence.correction.confirm"))}</p>` : `<p>${esc(preview.old_entity_id)} → ${esc(preview.new_entity_id)}</p>`}
         <p>${esc(t("coherence.replacement.api_help"))}</p>
         <p role="status" data-replacement-count>${esc(t("coherence.replacement.count", { count: selected, total: preview.replacement_count, files: preview.file_count }))}</p>
         ${preview.files_skipped ? `<ha-alert alert-type="warning">${esc(t("coherence.stats.skipped", { count: preview.files_skipped }))}</ha-alert>` : ""}
         ${preview.replacement_count ? `<div class="entity-replacement-list">${preview.replacements.map((row) => `
           <label class="entity-replacement-row">
             <ha-checkbox data-replacement-id="${esc(row.id)}" ${state.selected.has(row.id) ? "checked" : ""} ${state.busy ? "disabled" : ""} aria-label="${esc(`${row.source_name} · ${row.file}:${row.line}:${row.column}`)}"></ha-checkbox>
             <span>${correction ? `<strong>${esc(row.old_entity_id)} → ${esc(row.new_entity_id)}</strong><small>${esc(row.source_name)}</small>` : `<strong>${esc(row.source_name)}</strong>`}<small>${esc(t(`coherence.types.${row.source_type}`))} · ${esc(row.file)} · ${esc(t("coherence.replacement.location", row))}</small></span>
           </label>`).join("")}</div>` : `<p>${esc(t("coherence.replacement.empty"))}</p>`}`
      : correction ? `<p role="status">${esc(t(state.busy ? "coherence.replacement.busy" : "coherence.correction.confirm"))}</p>` : `<p>${esc(t("coherence.replacement.help"))}</p>
         <div class="entity-replacement-fields">
           <ha-selector data-replacement-field="old_entity_id" aria-label="${esc(t("coherence.replacement.old"))}"></ha-selector>
           <ha-selector data-replacement-field="new_entity_id" aria-label="${esc(t("coherence.replacement.new"))}"></ha-selector>
         </div>`;
  return `<ha-dialog id="entity-replacement-dialog" width="large" header-title="${esc(t(correction ? "coherence.correction.title" : preview && !state.result ? "coherence.replacement.preview_title" : "coherence.replacement.button"))}">
    <ha-icon-button slot="headerNavigationIcon" path="${MDI_CLOSE}" data-action="close-entity-replacement" aria-label="${esc(t("buttons.close"))}" ${state.busy ? "disabled" : ""}></ha-icon-button>
    <div class="entity-replacement-content">
      ${state.error ? `<ha-alert alert-type="error" role="alert">${esc(state.error)}</ha-alert>` : ""}
      ${content}
    </div>
    <ha-dialog-footer slot="footer">
      <ha-button slot="secondaryAction" appearance="plain" data-action="close-entity-replacement" ${state.busy ? "disabled" : ""}>${esc(t(state.result ? "buttons.close" : "buttons.cancel"))}</ha-button>
      ${preview && !state.result && !correction ? `<ha-button slot="secondaryAction" appearance="plain" data-action="back-entity-replacement" ${state.busy ? "disabled" : ""}>${esc(t("coherence.replacement.back"))}</ha-button>` : ""}
      ${state.result || (correction && !preview) ? "" : `<ha-button slot="primaryAction" appearance="accent" data-action="${preview ? "apply" : "preview"}-entity-replacement" ${state.busy || (preview && !selected) ? "disabled" : ""}>${esc(t(state.busy ? "coherence.replacement.busy" : correction ? "coherence.correction.button" : preview ? "coherence.replacement.apply" : "coherence.replacement.preview"))}</ha-button>`}
    </ha-dialog-footer>
  </ha-dialog>`;
}

export function hydrateEntityReplacement(root, context) {
  const dialog = root?.querySelector?.("#entity-replacement-dialog");
  const state = context._entityReplacement;
  if (!dialog || !state) return;
  dialog.hass = context._hass;
  dialog.preventScrimClose = state.busy;
  dialog.scrimClickAction = state.busy ? "" : "close";
  dialog.escapeKeyAction = state.busy ? "" : "close";
  if (!dialog.dataset.configured) {
    dialog.dataset.configured = "true";
    dialog.addEventListener("closed", (event) => {
      if (event.target !== dialog || context._entityReplacement !== state) return;
      if (state.busy) { dialog.open = true; return; }
      context._entityReplacement = null;
      context._render();
    });
  }
  const fields = dialog.querySelectorAll("[data-replacement-field]");
  const entityIds = new Set(fields.length ? [
    ...Object.keys(context._hass?.states ?? {}),
    ...Object.keys(context._hass?.entities ?? {}),
  ] : []);
  const options = [...entityIds].sort().map((value) => {
    const name = context._hass?.states?.[value]?.attributes?.friendly_name;
    return { value, label: name ? `${name} (${value})` : value };
  });
  fields.forEach((control) => {
    const field = control.dataset.replacementField;
    control.hass = context._hass;
    control.label = context._t(`coherence.replacement.${field === "old_entity_id" ? "old" : "new"}`);
    control.selector = { select: { options, custom_value: true, mode: "dropdown" } };
    control.value = state[field];
    control.disabled = state.busy;
    if (control.dataset.configured) return;
    control.dataset.configured = "true";
    control.addEventListener("value-changed", (event) => {
      if (state.busy) return;
      state[field] = String(event.detail?.value ?? "");
      control.value = state[field];
    });
  });
  dialog.querySelectorAll("[data-replacement-id]").forEach((checkbox) => {
    if (checkbox.dataset.configured) return;
    checkbox.dataset.configured = "true";
    checkbox.addEventListener("change", () => {
      if (state.busy) return;
      const id = checkbox.dataset.replacementId;
      if (checkbox.checked) state.selected.add(id);
      else state.selected.delete(id);
      dialog.querySelector("[data-replacement-count]").textContent = context._t("coherence.replacement.count", {
        count: state.selected.size, total: state.preview.replacement_count, files: state.preview.file_count,
      });
      dialog.querySelector('[data-action="apply-entity-replacement"]').disabled = !state.selected.size;
    });
  });
  dialog.open = true;
}

export async function handleEntityReplacementAction(action, button) {
  const correction = ["correct-coherence", "correct-selected-coherence"].includes(action);
  if (!correction && !["open", "close", "back", "preview", "apply"].some((prefix) => action === `${prefix}-entity-replacement`)) return false;
  if (this._readOnly || this._entityReplacement?.busy) return true;
  if (correction) {
    const rows = this._coherenceTableRows().filter((row) => row.selectable && (
      action === "correct-selected-coherence" ? this._selectedCoherenceIds.has(row.id) : row.index === Number(button?.dataset.rowIndex)
    ));
    if (!rows.length) return true;
    this._entityReplacement = {
      coherenceCorrection: true, scannedAt: this._coherence.scanned_at,
      rowIndices: rows.map((row) => row.index), selected: new Set(), busy: false,
    };
    action = "preview-entity-replacement";
  }
  if (action === "open-entity-replacement") {
    this._entityReplacement = { old_entity_id: "", new_entity_id: "", preview: null, selected: new Set(), busy: false, error: null, result: null };
  } else if (action === "close-entity-replacement") {
    this._entityReplacement = null;
  } else if (action === "back-entity-replacement") {
    this._entityReplacement.preview = null;
    this._entityReplacement.error = null;
  } else {
    const state = this._entityReplacement;
    if (!state) return true;
    state.error = null;
    state.busy = true;
    this._render();
    try {
      if (action === "preview-entity-replacement") {
        state.preview = state.coherenceCorrection
          ? await this._api.previewCoherenceCorrections(state.scannedAt, state.rowIndices)
          : await this._api.previewEntityReplacement(state.old_entity_id.trim(), state.new_entity_id.trim());
        state.selected = new Set(state.preview.replacements.map((row) => row.id));
      } else {
        if (!state.preview || !state.selected.size) return true;
        state.result = await this._api.applyEntityReplacement(state.preview.preview_id, [...state.selected]);
        if (state.coherenceCorrection) {
          this._selectedCoherenceIds.clear();
          try {
            this._coherence = await this._api.scanCoherence();
            this._coherenceScannedAt = this._coherence.scanned_at;
          } catch (error) {
            this._notice = { kind: "error", text: this._errorText(error) };
          }
        }
      }
    } catch (error) {
      const code = error?.code ?? error?.body?.code;
      state.error = ["replacement_entity_invalid", "replacement_entity_missing", "replacement_selection_invalid", "replacement_yaml_invalid", "replacement_preview_stale", "replacement_failed", "replacement_rollback_failed", "replacement_incomplete"].includes(code)
        ? this._t(`coherence.replacement.errors.${code}`) : this._errorText(error);
    } finally {
      state.busy = false;
      this._render();
    }
    return true;
  }
  this._render();
  return true;
}
