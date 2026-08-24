import assert from "node:assert/strict";
import test from "node:test";

globalThis.HTMLElement = class {
  constructor() {
    this.isConnected = true;
  }

  attachShadow() {
    this.shadowRoot = {
      addEventListener() {},
      querySelectorAll() { return []; },
      innerHTML: "",
    };
    return this.shadowRoot;
  }
};
globalThis.customElements = {
  _items: new Map(),
  define(name, value) { this._items.set(name, value); },
  get(name) { return this._items.get(name); },
};

const { durationText, lines, newRuleDefaults } = await import(
  "../frontend-src/alert-manager-panel.js"
);

test("human duration formatter", () => {
  assert.equal(durationText(45), "45 s");
  assert.equal(durationText(900), "15 min");
  assert.equal(durationText(7200), "2 h");
});

test("textarea list parser", () => {
  assert.deepEqual(lines("sensor.one\nsensor.two, sensor.three"), [
    "sensor.one",
    "sensor.two",
    "sensor.three",
  ]);
});

test("panel is registered", () => {
  assert.ok(customElements.get("alert-manager-panel"));
});

test("new rules start enabled with safe defaults", () => {
  assert.deepEqual(newRuleDefaults(), {
    name: "",
    entity_id: "",
    enabled: true,
    source: "state",
    attribute: "",
    operator: "equals",
    value: "",
    duration: 900,
    severity: "warning",
    message: "",
  });
});

test("unrelated Home Assistant updates do not rerender the overview", () => {
  const Panel = customElements.get("alert-manager-panel");
  const panel = new Panel();
  panel._config = { rules: [] };
  let renders = 0;
  panel._render = () => { renders += 1; };
  const sensor = {
    state: "0",
    attributes: { active_count: 0, pending_count: 0, alerts: [], pending: [] },
  };
  panel.hass = { states: { "sensor.alert_manager": sensor } };
  panel.hass = {
    states: { "sensor.alert_manager": sensor, "sensor.other": { state: "1" } },
  };
  assert.equal(renders, 1);
});
