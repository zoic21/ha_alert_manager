export class AlertManagerApi {
  constructor(getHass) {
    this._getHass = getHass;
  }

  call(message) {
    return this._getHass().callWS(message);
  }

  acknowledgeFor(alertId, duration) {
    return this.call({
      type: "alert_manager/alerts/acknowledgement/update",
      alert_ids: [alertId], acknowledged: true, duration,
    });
  }

  reevaluateAlert(alertId) {
    return this.call({ type: "alert_manager/alerts/reevaluate", alert_id: alertId });
  }

  exportEntities() {
    return this.call({ type: "alert_manager/coherence/entities/export" });
  }

  entityRenames() {
    return this.call({ type: "alert_manager/coherence/entity_renames/list" });
  }

  previewEntityReplacement(oldEntityId, newEntityId) {
    return this.call({
      type: "alert_manager/coherence/entity_replacement/preview",
      old_entity_id: oldEntityId, new_entity_id: newEntityId,
    });
  }

  async applyEntityReplacement(previewId, occurrenceIds) {
    const message = { preview_id: previewId, occurrence_ids: occurrenceIds };
    const plan = await this.call({ type: "alert_manager/coherence/entity_replacement/prepare", ...message });
    const written = [];
    try {
      for (const update of plan.native_updates) {
        const path = `config/${update.domain}/config/${encodeURIComponent(update.key)}`;
        const current = await this._getHass().callApi("GET", path);
        if (!sameReplacementConfiguration(current, update.before)) {
          throw Object.assign(new Error("replacement_preview_stale"), { code: "replacement_preview_stale" });
        }
        written.push({ path, before: update.before });
        await this._getHass().callApi("POST", path, update.after);
      }
      return await this.call({ type: "alert_manager/coherence/entity_replacement/apply", ...message });
    } catch (error) {
      for (const update of written.reverse()) {
        await this._getHass().callApi("POST", update.path, update.before);
      }
      throw error;
    }
  }

  testRule(rule, ruleId = "") {
    return this.call({
      type: "alert_manager/rules/test",
      rule,
      ...(ruleId ? { rule_id: ruleId } : {}),
    });
  }
}

function sameReplacementConfiguration(left, right) {
  if (left === right) return true;
  if (!left || !right || typeof left !== "object" || typeof right !== "object") return false;
  const keys = Object.keys(left);
  return keys.length === Object.keys(right).length
    && keys.every((key) => Object.hasOwn(right, key) && sameReplacementConfiguration(left[key], right[key]));
}
