import { AlertManagerApi } from "./transport.js";
import { integrationStates } from "../utils/integration-entities.js";

const dashboardConnections = new WeakMap();

// One fetch per revision and connection, regardless of the number of cards.
export function connectDashboard(hass, listener) {
  const connection = hass.connection;
  let state = dashboardConnections.get(connection);
  if (!state) {
    state = { listeners: new Set(), hass, value: { status: "loading" }, revision: null,
      generation: 0, fetching: false, requested: false, closed: false, identities: null };
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
              state.identities = snapshot;
              const observed = state.observe();
              state.revision = observed.revision;
              state.publish(observed.status ? { status: observed.status } : { status: "ready", snapshot });
            }
          } catch (error) {
            if (generation === state.generation) state.publish({
              status: error?.code === "unauthorized" ? "admin" : "unavailable",
            });
          }
        }
      } finally {
        state.fetching = false;
      }
    };
    state.update = (next, force = false) => {
      state.hass = next;
      if (connection.connected === false) {
        state.disconnected();
        return;
      }
      const { status, revision, missing } = state.observe();
      if (!force && revision === state.revision) return;
      state.revision = revision;
      state.generation += 1;
      if (status) {
        state.requested = false;
        state.publish({ status });
        // Discover registry identities once when defaults or previous names vanish.
        if (missing) void state.refresh();
      } else {
        if (state.value.status !== "ready") state.publish({ status: "loading" });
        void state.refresh();
      }
    };
    state.disconnected = () => {
      state.generation += 1;
      state.requested = false;
      // A transport reconnect is transient; retain the last successful snapshot.
      if (state.value.status !== "ready") state.publish({ status: "unavailable" });
    };
    state.ready = () => state.update(state.hass, true);
    connection.addEventListener("disconnected", state.disconnected);
    connection.addEventListener("ready", state.ready);
    dashboardConnections.set(connection, state);
  }
  state.listeners.add(listener);
  listener(state.value);
  state.update(hass);
  return {
    update: (next) => state.update(next),
    retry: () => state.update(state.hass, true),
    disconnect: () => {
      state.listeners.delete(listener);
      if (state.listeners.size) return;
      state.closed = true;
      connection.removeEventListener("disconnected", state.disconnected);
      connection.removeEventListener("ready", state.ready);
      dashboardConnections.delete(connection);
    },
  };
}
