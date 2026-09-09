import { AlertManagerApi } from "./transport.js";

const dashboardConnections = new WeakMap();

// One fetch per revision and connection, regardless of the number of cards.
export function connectDashboard(hass, listener) {
  const connection = hass.connection;
  let state = dashboardConnections.get(connection);
  if (!state) {
    state = { listeners: new Set(), hass, value: { status: "loading" }, revision: null,
      generation: 0, fetching: false, requested: false, closed: false };
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
            if (generation === state.generation) state.publish({ status: "ready", snapshot });
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
      const sensor = next.states?.["sensor.alert_manager_main_active"];
      const monitoring = next.states?.["switch.alert_manager_main_monitoring"];
      const status = connection.connected === false || !sensor || !monitoring
          || ["unavailable", "unknown"].includes(sensor.state)
          || ["unavailable", "unknown"].includes(monitoring.state) ? "unavailable"
          : monitoring.state === "off" ? "paused" : null;
      const revision = JSON.stringify([status, sensor?.state,
        sensor?.attributes?.alerts_revision, sensor?.attributes?.runtime?.startup]);
      if (!force && revision === state.revision) return;
      state.revision = revision;
      state.generation += 1;
      if (status) {
        state.requested = false;
        state.publish({ status });
      } else {
        if (state.value.status !== "ready") state.publish({ status: "loading" });
        void state.refresh();
      }
    };
    state.disconnected = () => {
      state.generation += 1;
      state.requested = false;
      state.publish({ status: "unavailable" });
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
