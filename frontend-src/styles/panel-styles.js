import { baseStyles } from "./base-styles.js";
import { tableStyles } from "./table-styles.js";
import { settingsStyles } from "./settings-styles.js";
import { ruleEditorStyles } from "./rule-editor-styles.js";
import { stateStyles } from "./state-styles.js";
import { responsiveStyles } from "./responsive-styles.js";

export const panelStyles = () => [
  baseStyles,
  tableStyles,
  settingsStyles,
  ruleEditorStyles,
  stateStyles,
  responsiveStyles,
].join("\n\n");
