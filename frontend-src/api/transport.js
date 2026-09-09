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

  testRule(rule, ruleId = "") {
    return this.call({
      type: "alert_manager/rules/test",
      rule,
      ...(ruleId ? { rule_id: ruleId } : {}),
    });
  }
}
