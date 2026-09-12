// Canonical automatic-pack fixtures shared by UI interaction regressions.
export function automaticPacks() {
  return ["unavailable", "connectivity", "unifi", "battery", "execution_errors", "flapping"].map((id) => {
    const numbers = id === "battery" ? [{ id: "threshold", default: 15, unit: "%" }]
      : id === "execution_errors" ? [{ id: "failure_threshold", default: 1 }]
      : id === "flapping" ? [{ id: "occurrences", default: 5 }, { id: "window", default: 3600, unit: "s" }, { id: "recovery", default: 1800, unit: "s" }] : [];
    const scalar = numbers.map((field) => ({ type: "number", translation_key: field.id, ...field }));
    const fields = [{ id: "enabled", translation_key: "monitoring", type: "boolean" }, ...(id === "flapping" ? [] : [{ id: "delay", translation_key: "trigger_delay", type: "number", unit: "s" }]), ...scalar];
    const maps = ["device", "entity"].map((kind) => ({ id: `${kind}_overrides`, translation_key: `${kind}_overrides`, type: `${kind}_settings_map`, default: {}, sparse: true, fields }));
    return { id, translation_key: id, available: true, prerequisites: id === "unifi" ? ["unifi"] : [], uses_delay: id !== "flapping", target_filter: id === "battery" ? { domain: "sensor", device_class: "battery" } : id === "execution_errors" ? { domain: ["automation", "script"] } : {}, config_fields: [...scalar, ...(id === "flapping" ? [{ id: "source_packs", type: "pack_settings_map", fields: [...scalar, ...maps] }] : []), ...maps] };
  });
}
export function automaticConfig() {
  return Object.fromEntries(automaticPacks().map((pack) => [pack.id, {
    enabled: true, label_ids: [], ...(pack.uses_delay ? { delay: pack.id === "execution_errors" ? 0 : 900 } : { source_packs: { unavailable: {} } }),
    ...Object.fromEntries(pack.config_fields.filter((field) => field.type === "number").map((field) => [field.id, field.default])),
    device_overrides: {}, entity_overrides: pack.id === "execution_errors" ? { "automation.test": { failure_threshold: 3 } } : {},
  }]));
}
