import { ALERT_MANAGER_ENTITY_IDS } from "./constants.js";

export function integrationEntityId(snapshot, defaultId) {
  return snapshot?.entity_ids?.[defaultId] || defaultId;
}

// Keep stable role keys for consumers while resolving renamed HA entities.
export function integrationStates(hass, snapshot) {
  return Object.fromEntries(ALERT_MANAGER_ENTITY_IDS.map((defaultId) => [
    defaultId, hass?.states?.[integrationEntityId(snapshot, defaultId)],
  ]));
}
