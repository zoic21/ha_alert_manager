import assert from "node:assert/strict";
import test from "node:test";

const tick = () => new Promise((resolve) => setImmediate(resolve));

class NativeElement extends EventTarget {
  attachShadow() { this.shadowRoot = new EventTarget(); }
}

function registry(native) {
  const definitions = new Map();
  const awaiting = new Map();
  return {
    get: (name) => definitions.get(name),
    define(name, constructor) {
      assert.equal(definitions.has(name), false, `Duplicate definition: ${name}`);
      definitions.set(name, constructor);
      // The scoped registry registers stand-ins with the native registry. Its
      // private definition map does not inherit previously registered elements.
      if (native && !native.get(name)) native.define(name, constructor);
      awaiting.get(name)?.(constructor);
    },
    whenDefined(name) {
      if (definitions.has(name)) return Promise.resolve(definitions.get(name));
      return new Promise((resolve) => awaiting.set(name, resolve));
    },
  };
}

for (const [name, path] of [
  ["source modules", "../frontend-src/dashboard/card.js"],
  ["distributed bundle", "../custom_components/alert_manager/frontend/alert-manager-card.js"],
]) {
  test(`${name} wait for HA's registry and HTMLElement replacement before registering`, async () => {
    const nativeRegistry = registry();
    globalThis.customElements = nativeRegistry;
    globalThis.HTMLElement = NativeElement;
    globalThis.window = { customCards: [] };
    const importing = import(path);
    // Allow ESM dependencies to load and reach the frontend readiness barrier.
    // Wait on the observed call, rather than assuming a fixed import latency.
    let reachedBarrier;
    const barrier = new Promise((resolve) => { reachedBarrier = resolve; });
    const whenDefined = nativeRegistry.whenDefined;
    nativeRegistry.whenDefined = (tag) => {
      assert.equal(tag, "home-assistant");
      reachedBarrier();
      return whenDefined(tag);
    };
    await barrier;
    await tick();
    assert.equal(nativeRegistry.get("alert-manager-card"), undefined);
    assert.equal(nativeRegistry.get("alert-manager-card-editor"), undefined);
    assert.equal(window.customCards.length, 0);

    // Reproduce app.ts: install the polyfill, then define the HA shell.
    class PolyfilledElement extends NativeElement {}
    const haRegistry = registry(nativeRegistry);
    globalThis.customElements = haRegistry;
    globalThis.HTMLElement = PolyfilledElement;
    haRegistry.define("home-assistant", class extends PolyfilledElement {});
    await importing;

    const Card = haRegistry.get("alert-manager-card");
    const Editor = haRegistry.get("alert-manager-card-editor");
    assert.ok(Card, "Lovelace must find the card in the current registry");
    assert.ok(Editor);
    assert.equal(Object.getPrototypeOf(Card), PolyfilledElement);
    assert.equal(Object.getPrototypeOf(Editor), PolyfilledElement);
    assert.ok(new Card() instanceof PolyfilledElement);
    assert.equal(window.customCards.length, 1);
    for (const entry of window.customCards) assert.ok(haRegistry.get(entry.type));
  });
}
