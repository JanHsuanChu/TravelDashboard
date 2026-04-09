import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, "..");

const templatePath = join(root, "README.template.md");
const architecturePath = join(root, "docs", "architecture.md");
const outPath = join(root, "README.md");

const marker = "{{ARCHITECTURE_BODY}}";

function normalizeArchitectureForReadme(md) {
  const trimmed = md.replace(/^\uFEFF/, "").trimEnd();
  const lines = trimmed.split("\n");
  if (lines.length > 0 && lines[0].startsWith("# ")) {
    lines[0] = "### " + lines[0].slice(2);
  }
  return lines.join("\n").trimEnd() + "\n";
}

const template = readFileSync(templatePath, "utf8");
if (!template.includes(marker)) {
  throw new Error(`README.template.md must contain ${marker}`);
}

const architecture = readFileSync(architecturePath, "utf8");
const body = normalizeArchitectureForReadme(architecture);

const banner =
  "<!-- This file is generated. Edit README.template.md and docs/architecture.md, then run: npm run readme -->\n\n";

const output = banner + template.replace(marker, body);
writeFileSync(outPath, output, "utf8");
console.log("Wrote README.md from README.template.md + docs/architecture.md");
