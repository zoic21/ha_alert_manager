import { AlertManagerApi } from "./transport.js";
import { integrationStates } from "../utils/integration-entities.js";

const dashboardConnections = new WeakMap();
const dashboardRetryDelays = [1000, 3000];
const dashboardDisconnectDelay = 5000;

// One fetch per revision and connection, regardless of the number of cards.
export function connectDashboard(hass, listener) {
  const connection = hass.connection;
  let state = dashboardConnections.get(connection);
  if (!state || state.closed) {
    // Retain one snapshot per HA connection when navigation recreates the cards.
    const cached = state;
    state = { listeners: new Set(), hass,
      value: cached?.value.status === "ready" ? cached.value : { status: "loading" }, revision: null,
      generation: 0, fetching: false, requested: false, closed: false, identities: cached?.identities ?? null,
      retryTimer: null, disconnectTimer: null, retryAttempts: 0 };
    state.clearRecovery = () => {
      clearTimeout(state.retryTimer);
      clearTimeout(state.disconnectTimer);
      state.retryTimer = null;
      state.disconnectTimer = null;
      state.retryAttempts = 0;
    };
    state.observe = () => {
      const states = integrationStates(state.hass, state.identities);
      const sensor = states["sensor.alert_manager_main_active"];
      const monitoring = states["switch.alert_manager_main_monitoring"];
      const missing = !sensor || !monitoring;
      const status = missing
          || ["unavailable", "unknown"].includes(sensor.state)
          || ["unavailable", "unknown"].includes(monitoring.state) ? "unavailable"
          : monitoring.state === "off" ? "paused" : null;
      const revision = JSON.stringify([status, sensor?.state,
        sensor?.attributes?.alerts_revision, sensor?.attributes?.runtime?.startup]);
      return { status, revision, missing };
    };
    state.publish = (value) => {
      if (state.closed) return;
      state.value = value;
      for (const callback of state.listeners) callback(value);
    };
    state.retryLater = () => {
      // A suspended page resumes recovery through its visibility listener.
      if (globalThis.document?.visibilityState === "hidden") return;
      if (state.retryAttempts === dashboardRetryDelays.length) {
        state.publish({ status: "unavailable" });
        return;
      }
      state.retryTimer = setTimeout(() => {
        state.retryTimer = null;
        if (globalThis.document?.visibilityState === "hidden") return;
        if (connection.connected === false) state.disconnected();
        else void state.refresh();
      }, dashboardRetryDelays[state.retryAttempts++]);
    };
    state.refresh = async () => {
      state.requested = true;
      if (state.fetching || state.closed) return;
      state.fetching = true;
      try {
        while (state.requested && !state.closed) {
          state.requested = false;
          const generation = state.generation;
          try {
            const snapshot = await new AlertManagerApi(() => state.hass).call({
              type: "alert_manager/alerts/list",
            });
            if (!Array.isArray(snapshot?.alerts)) throw new Error("Invalid alert snapshot");
            if (generation === state.generation) {
              state.clearRecovery();
              state.identities = snapshot;
              const observed = state.observe();
              state.revision = observed.revision;
              state.publish(observed.status ? { status: observed.status } : { status: "ready", snapshot });
            }
          } catch (error) {
            if (state.closed || generation !== state.generation) continue;
            if (error?.code === "unauthorized") {
              state.clearRecovery();
              state.publish({ status: "admin" });
            } else {
              // Keep the previous display during bounded recovery, even if empty.
              state.retryLater();
            }
          }
        }
      } finally {
        state.fetching = false;
      }
    };
    state.update = (next, force = false) => {
      if (state.closed) return;
      state.hass = next;
      if (connection.connected === false) {
        state.disconnected();
        return;
      }
      const { status, revision, missing } = state.observe();
      if (!force && revision === state.revision) return;
      state.clearRecovery();
      state.revision = revision;
      state.generation += 1;
      if (status) {
        state.requested = false;
        // Discover registry identities once when defaults or previous names vanish.
        if (missing) void state.refresh();
        else state.publish({ status });
      } else {
        if (state.value.status !== "ready") state.publish({ status: "loading" });
        void state.refresh();
      }
    };
    state.disconnected = () => {
      state.generation += 1;
      state.requested = false;
      state.revision = null;
      clearTimeout(state.retryTimer);
      state.retryTimer = null;
      if (globalThis.document?.visibilityState === "hidden") return;
      if (state.disconnectTimer !== null || state.value.status === "unavailable") return;
      // Allow a short transport interruption, but never hide a persistent outage.
      state.disconnectTimer = setTimeout(() => {
        state.disconnectTimer = null;
        if (globalThis.document?.visibilityState !== "hidden") state.publish({ status: "unavailable" });
      }, dashboardDisconnectDelay);
    };
    state.ready = () => state.update(state.hass, true);
    state.visible = () => {
      if (globalThis.document?.visibilityState === "visible") state.ready();
    };
    connection.addEventListener("disconnected", state.disconnected);
    connection.addEventListener("ready", state.ready);
    globalThis.document?.addEventListener?.("visibilitychange", state.visible);
    dashboardConnections.set(connection, state);
  }
  state.listeners.add(listener);
  listener(state.value);
  state.update(hass);
  return {
    update: (next) => state.update(next),
    retry: () => state.update(state.hass, true),
    disconnect: () => {
      if (state.closed) return;
      state.listeners.delete(listener);
      if (state.listeners.size) return;
      state.closed = true;
      state.clearRecovery();
      connection.removeEventListener("disconnected", state.disconnected);
      connection.removeEventListener("ready", state.ready);
      globalThis.document?.removeEventListener?.("visibilitychange", state.visible);
    },
  };
}
