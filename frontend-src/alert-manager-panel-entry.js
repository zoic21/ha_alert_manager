import { AlertManagerPanel } from "./alert-manager-panel.js";

const narrowDescriptor = Object.getOwnPropertyDescriptor(AlertManagerPanel.prototype, "narrow");

Object.defineProperty(AlertManagerPanel.prototype, "narrow", {
  configurable: true,
  set(value) {
    narrowDescriptor?.set?.call(this, value);
    const table = this.shadowRoot?.querySelector?.("#coherence-table");
    if (table) table.narrow = Boolean(this._narrow);
  },
});

AlertManagerPanel.prototype._nativeCoherenceEntityCell = function(row, narrow = false) {
  if (!narrow || !globalThis.document?.createElement) return row.entity;
  const content = document.createElement("span");
  content.style.cssText = "display:flex;min-width:0;flex-direction:column;line-height:1.35";

  const primary = document.createElement("span");
  primary.textContent = row.entity;
  primary.style.cssText = "overflow:hidden;color:var(--primary-text-color,#212121);font-weight:var(--ha-font-weight-medium,500);text-overflow:ellipsis;white-space:nowrap";

  const secondary = document.createElement("span");
  secondary.textContent = [row.type, row.source, row.file, row.line]
    .filter((value) => value !== undefined && value !== null && value !== "")
    .join(" · ");
  secondary.style.cssText = "display:block;min-width:0;overflow:hidden;color:var(--secondary-text-color,#727272);font-weight:var(--ha-font-weight-normal,400);text-overflow:ellipsis;white-space:nowrap";

  content.append(primary, secondary);
  return content;
};

AlertManagerPanel.prototype._openCoherenceLink = function(link) {
  if (link?.type === "more_info") {
    this._openMoreInfo(link.entity_id);
  } else if (link?.type === "navigate") {
    this._navigate(link.path, true);
  }
};

const hydrateCoherenceTable = AlertManagerPanel.prototype._hydrateCoherenceTable;
AlertManagerPanel.prototype._hydrateCoherenceTable = function() {
  hydrateCoherenceTable.call(this);
  const table = this.shadowRoot?.querySelector?.("#coherence-table");
  if (!table || !this._coherence) return;

  table.narrow = Boolean(this._narrow);
  table.clickable = true;
  if (table.columns?.entity) {
    table.columns = {
      ...table.columns,
      entity: {
        ...table.columns.entity,
        template: (row) => this._nativeCoherenceEntityCell(row, Boolean(this._narrow)),
      },
    };
  }
  table._alertManagerRows = table.data;
  table.addEventListener("row-click", (event) => {
    const row = table._alertManagerRows?.find(
      (item) => String(item.id) === String(event.detail?.id),
    );
    if (row?.link) this._openCoherenceLink(row.link);
  });
};
