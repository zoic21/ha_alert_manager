import { readFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";

const file = new URL("../frontend-src/alert-manager-panel.js", import.meta.url);
const result = spawnSync(process.execPath, ["--check", file.pathname], {
  encoding: "utf8",
});
if (result.status !== 0) {
  process.stderr.write(result.stderr);
  process.exit(result.status ?? 1);
}

const source = await readFile(file, "utf8");
const forbidden = ["eval(", "new Function(", "document.cookie", "localStorage"];
for (const token of forbidden) {
  if (source.includes(token)) {
    throw new Error(`Forbidden frontend construct: ${token}`);
  }
}
if (!source.includes("customElements.define")) {
  throw new Error("Panel custom element is not registered");
}
console.log("Frontend syntax and safety checks passed");
