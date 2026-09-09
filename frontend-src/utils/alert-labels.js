export function alertLabelIds(source, hass) {
  return [...new Set([
    ...(Array.isArray(source.labels) ? source.labels : []),
    ...(Array.isArray(hass?.entities?.[source.entity_id]?.labels)
      ? hass.entities[source.entity_id].labels : []),
  ].map(String).filter(Boolean))];
}
