import { esc } from "../utils/escaping.js";

// Keep the native selector's object value at the UI boundary; persistence uses seconds.
export function durationFieldValue(field) {
  if (!field?.dataset || !("durationValue" in field.dataset)) return field?.value;
  const value = field.value;
  if (value === undefined || value === null) return field.required ? NaN : "";
  if (typeof value !== "object") return value;
  let seconds = 0;
  for (const [key, factor] of [["hours", 3600], ["minutes", 60], ["seconds", 1]]) {
    const part = Number(value[key] ?? 0);
    if (!Number.isSafeInteger(part) || part < 0) return NaN;
    seconds += part * factor;
  }
  return Number.isSafeInteger(seconds) ? seconds : NaN;
}

export function durationSelectorValue(value) {
  if (value === "" || value === null || value === undefined) return undefined;
  const seconds = Number(value);
  return {
    hours: Math.floor(seconds / 3600),
    minutes: Math.floor(seconds / 60) % 60,
    seconds: seconds % 60,
  };
}

export function renderDurationControl(id, label, value, min, max, options = {}) {
  const { required = true, nameMode = "id", attributes = {} } = options;
  const attrs = Object.entries(attributes).map(([key, item]) => `${key}="${esc(item)}"`).join(" ");
  return `<ha-selector ${id ? `id="${esc(id)}"` : ""} ${nameMode === "name" ? `data-field="${esc(id)}"` : ""} data-duration-value="${esc(value ?? "")}" data-duration-min="${min}" data-duration-max="${max}" data-duration-required="${required}" ${attrs} aria-label="${esc(label)}"></ha-selector>`;
}

export function renderDurationField(id, label, value, min, max, options = {}) {
  return `<div class="field duration-field"><span class="field-label">${esc(label)}</span>${renderDurationControl(id, label, value, min, max, options)}${options.help ? `<small>${esc(options.help)}</small>` : ""}</div>`;
}

export function hydrateDurationFields(root, panel, onChange) {
  root?.querySelectorAll?.("[data-duration-value]").forEach((field) => {
    field.hass = panel._hass;
    if (panel._configuredControls.has(field)) return;
    field.selector = { duration: { enable_day: false, enable_millisecond: false, enable_second: true } };
    field.required = field.dataset.durationRequired === "true";
    field.value = durationSelectorValue(field.dataset.durationValue);
    // Internal input/change events precede value-changed and still carry the old value.
    for (const type of ["input", "change"]) field.addEventListener(type, (event) => event.stopPropagation());
    field.addEventListener("value-changed", (event) => {
      event.stopPropagation();
      field.value = event.detail?.value;
      if (onChange) onChange(field);
      else panel._handleInput({ target: field });
    });
    panel._configuredControls.add(field);
  });
}

export function validateDurationFields(root, panel) {
  let valid = true;
  for (const field of root?.querySelectorAll?.("[data-duration-value]") ?? []) {
    const value = durationFieldValue(field);
    const min = Number(field.dataset.durationMin);
    const max = Number(field.dataset.durationMax);
    const fieldValid = (value === "" && !field.required)
      || (Number.isSafeInteger(value) && value >= min && value <= max);
    field.helper = fieldValid ? undefined : panel._t("errors.duration_field_bounds", {
      min: panel._durationText(min), max: panel._durationText(max),
    });
    if (!fieldValid) field.reportValidity?.();
    valid = fieldValid && valid;
  }
  return valid;
}
