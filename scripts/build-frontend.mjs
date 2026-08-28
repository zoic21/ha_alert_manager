import { copyFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";

const files = [
  "alert-manager-panel.js",
  "alert-manager-panel-entry.js",
  "alert-manager-panel-runtime.js",
];

for (const filename of files) {
  const source = new URL(`../frontend-src/${filename}`, import.meta.url);
  const destination = new URL(
    `../custom_components/alert_manager/frontend/${filename}`,
    import.meta.url,
  );
  await mkdir(dirname(destination.pathname), { recursive: true });
  await copyFile(source, destination);
  console.log(`Built ${filename}`);
}
