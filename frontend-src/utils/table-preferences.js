const TABLE_PREFERENCES_KEY = "alert-manager-table-preferences-v1";

const COHERENCE_TABLE_PREFERENCES_KEY = "alert-manager-coherence-table-preferences-v1";

const RULES_TABLE_PREFERENCES_KEY = "alert-manager-rules-table-preferences-v1";

const COHERENCE_STALE_MS = 48 * 60 * 60 * 1000;

const COHERENCE_COLUMNS = ["entity", "type", "source", "file", "line", "action"];

const COHERENCE_SECONDARY_COLUMNS = new Set(["type", "source", "file", "line"]);

const RULES_COLUMNS = ["name", "entities", "condition", "duration", "enabled"];

const RULES_SECONDARY_COLUMNS = new Set(["entities", "condition", "duration"]);

const DEFAULT_COHERENCE_TABLE_STATE = Object.freeze({
  columnOrder: Object.freeze([...COHERENCE_COLUMNS]),
  hiddenColumns: Object.freeze([]),
  sortBy: "entity",
  sortDirection: "asc",
  groupBy: "",
});

const DEFAULT_RULES_TABLE_STATE = Object.freeze({
  columnOrder: Object.freeze([...RULES_COLUMNS]),
  hiddenColumns: Object.freeze([]),
  sortBy: "name",
  sortDirection: "asc",
});

const REQUIRED_COLUMNS = new Set(["status", "entity"]);

const DEFAULT_TABLE_STATE = Object.freeze({
  overview: Object.freeze({
    columns: Object.freeze(["status", "entity", "device", "rule", "integration", "timeline"]),
    groupBy: "none",
    sortBy: "status",
    sortDirection: "asc",
  }),
  history: Object.freeze({
    columns: Object.freeze(["status", "entity", "device", "rule", "integration", "detected"]),
    groupBy: "none",
    sortBy: "detected",
    sortDirection: "desc",
  }),
});

const makeTableState = (kind, preferences = {}) => {
  const defaults = DEFAULT_TABLE_STATE[kind];
  const storedPreferences = preferences && typeof preferences === "object"
    ? preferences
    : {};
  const sortOptions = kind === "history"
    ? ["status", "device", "entityName", "rule", "integration", "value", "detected", "resolved"]
    : ["status", "device", "entityName", "rule", "integration", "value", "detected", "activated", "remaining"];
  const savedColumns = Array.isArray(storedPreferences.columns)
    ? storedPreferences.columns.filter((column, index, columns) => (
      typeof column === "string" && columns.indexOf(column) === index
    ))
    : [];
  const legacyDefaults = kind === "overview"
    ? [
      ["status", "device", "entity", "value", "condition", "detected", "timeline"],
      ["status", "entity", "device", "value", "condition", "detected", "timeline"],
    ]
    : [
      ["status", "device", "entity", "value", "condition", "detected", "resolved"],
      ["status", "entity", "device", "value", "condition", "detected", "resolved"],
    ];
  const isLegacyDefault = legacyDefaults.some((legacyDefault) => (
    savedColumns.length === legacyDefault.length
    && savedColumns.every((column, index) => column === legacyDefault[index])
  ));
  const usesPreviousOverviewDefaultSort = kind === "overview"
    && storedPreferences.sortBy === "detected"
    && storedPreferences.sortDirection === "desc";
  const columns = savedColumns.length && !isLegacyDefault ? [...savedColumns] : [...defaults.columns];
  for (const required of REQUIRED_COLUMNS) {
    if (!columns.includes(required)) columns.push(required);
  }
  return {
    search: "",
    filters: {
      status: kind === "overview" ? ["active"] : [],
      device: [],
      area: [],
      rule: [],
      integration: [],
      labels: [],
      domain: [],
      entity: [],
      detectedFrom: "",
      detectedTo: "",
      resolvedFrom: "",
      resolvedTo: "",
    },
    columns,
    groupBy: ["none", "device", "area", "rule", "status"].includes(storedPreferences.groupBy)
      ? storedPreferences.groupBy
      : defaults.groupBy,
    sortBy: sortOptions.includes(storedPreferences.sortBy) && !usesPreviousOverviewDefaultSort
      ? storedPreferences.sortBy
      : defaults.sortBy,
    sortDirection: ["asc", "desc"].includes(storedPreferences.sortDirection)
      && !usesPreviousOverviewDefaultSort
      ? storedPreferences.sortDirection
      : defaults.sortDirection,
  };
};

export function loadTablePreferences() {
    let saved = {};
    try {
      saved = JSON.parse(window.localStorage?.getItem(TABLE_PREFERENCES_KEY) ?? "{}");
    } catch (_error) {
      saved = {};
    }
    return {
      overview: makeTableState("overview", saved?.overview),
      history: makeTableState("history", saved?.history),
    };
}

export function saveTablePreferences() {
    const preferences = Object.fromEntries(["overview", "history"].map((kind) => {
      const state = this._tableState[kind];
      return [kind, {
        columns: [...state.columns],
        groupBy: state.groupBy,
        sortBy: state.sortBy,
        sortDirection: state.sortDirection,
      }];
    }));
    try {
      window.localStorage?.setItem(TABLE_PREFERENCES_KEY, JSON.stringify(preferences));
    } catch (_error) {
      // Private browsing or a full storage quota must not make the panel unusable.
    }
}

export function ensureCoherenceTableState() {
    if (this._coherenceTableState) return this._coherenceTableState;
    let stored = {};
    try {
      stored = JSON.parse(window.localStorage?.getItem(COHERENCE_TABLE_PREFERENCES_KEY) ?? "{}");
    } catch (_error) {
      stored = {};
    }
    const storedOrder = Array.isArray(stored.columnOrder)
      ? stored.columnOrder.filter((column, index, columns) => (
        COHERENCE_COLUMNS.includes(column) && columns.indexOf(column) === index
      ))
      : [];
    this._coherenceTableState = {
      search: "",
      columnOrder: [
        ...storedOrder,
        ...COHERENCE_COLUMNS.filter((column) => !storedOrder.includes(column)),
      ],
      hiddenColumns: Array.isArray(stored.hiddenColumns)
        ? stored.hiddenColumns.filter((column) => (
          COHERENCE_COLUMNS.includes(column) && column !== "entity"
        ))
        : [],
      sortBy: COHERENCE_COLUMNS.includes(stored.sortBy) && stored.sortBy !== "action"
        ? stored.sortBy
        : DEFAULT_COHERENCE_TABLE_STATE.sortBy,
      sortDirection: ["asc", "desc"].includes(stored.sortDirection)
        ? stored.sortDirection
        : DEFAULT_COHERENCE_TABLE_STATE.sortDirection,
      groupBy: stored.groupBy === "entity" ? "entity" : "",
    };
    return this._coherenceTableState;
}

export function saveCoherenceTableState() {
    const state = this._ensureCoherenceTableState();
    try {
      window.localStorage?.setItem(COHERENCE_TABLE_PREFERENCES_KEY, JSON.stringify({
        columnOrder: state.columnOrder,
        hiddenColumns: state.hiddenColumns,
        sortBy: state.sortBy,
        sortDirection: state.sortDirection,
        groupBy: state.groupBy,
      }));
    } catch (_error) {
      // Private browsing or a full storage quota must not make the panel unusable.
    }
}

export function ensureRulesTableState() {
    if (this._tableState.rules) return this._tableState.rules;
    let stored = {};
    try {
      stored = JSON.parse(window.localStorage?.getItem(RULES_TABLE_PREFERENCES_KEY) ?? "{}");
    } catch (_error) {
      stored = {};
    }
    const storedOrder = Array.isArray(stored.columnOrder)
      ? stored.columnOrder.filter((column, index, columns) => (
        RULES_COLUMNS.includes(column) && columns.indexOf(column) === index
      ))
      : [];
    const optionalOrder = storedOrder.filter((column) => RULES_SECONDARY_COLUMNS.has(column));
    this._tableState.rules = {
      search: "",
      filters: { enabled: [] },
      columnOrder: [
        "name",
        ...optionalOrder,
        ...RULES_COLUMNS.filter((column) => (
          RULES_SECONDARY_COLUMNS.has(column) && !optionalOrder.includes(column)
        )),
        "enabled",
      ],
      hiddenColumns: Array.isArray(stored.hiddenColumns)
        ? stored.hiddenColumns.filter((column) => RULES_SECONDARY_COLUMNS.has(column))
        : [],
      sortBy: RULES_COLUMNS.includes(stored.sortBy)
        ? stored.sortBy
        : DEFAULT_RULES_TABLE_STATE.sortBy,
      sortDirection: ["asc", "desc"].includes(stored.sortDirection)
        ? stored.sortDirection
        : DEFAULT_RULES_TABLE_STATE.sortDirection,
    };
    return this._tableState.rules;
}

export function saveRulesTableState() {
    const state = this._ensureRulesTableState();
    try {
      window.localStorage?.setItem(RULES_TABLE_PREFERENCES_KEY, JSON.stringify({
        columnOrder: state.columnOrder,
        hiddenColumns: state.hiddenColumns,
        sortBy: state.sortBy,
        sortDirection: state.sortDirection,
      }));
    } catch (_error) {
      // Private browsing or a full storage quota must not make the panel unusable.
    }
}

export { TABLE_PREFERENCES_KEY, COHERENCE_TABLE_PREFERENCES_KEY, RULES_TABLE_PREFERENCES_KEY, COHERENCE_STALE_MS, COHERENCE_COLUMNS, COHERENCE_SECONDARY_COLUMNS, RULES_COLUMNS, RULES_SECONDARY_COLUMNS, DEFAULT_COHERENCE_TABLE_STATE, DEFAULT_RULES_TABLE_STATE, REQUIRED_COLUMNS, DEFAULT_TABLE_STATE, makeTableState };
