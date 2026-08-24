import { copyFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";

const source = new URL("../frontend-src/alert-manager-panel.js", import.meta.url);
const destination = new URL(
  "../custom_components/alert_manager/frontend/alert-manager-panel.js",
  import.meta.url,
);

await mkdir(dirname(destination.pathname), { recursive: true });
await copyFile(source, destination);
console.log("Built alert-manager-panel.js");
