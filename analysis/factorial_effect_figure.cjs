#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const moduleRoot = process.env.CODEX_NODE_MODULES;
if (!moduleRoot) throw new Error("CODEX_NODE_MODULES is required");
const pnpmRoot = path.join(moduleRoot, ".pnpm");
process.env.NODE_PATH = [moduleRoot, path.join(pnpmRoot, "node_modules")].join(path.delimiter);
require("module").Module._initPaths();
const sharpPackage = fs.readdirSync(pnpmRoot).find(name => name.startsWith("sharp@"));
if (!sharpPackage) throw new Error("bundled sharp package was not found");
const sharp = require(path.join(pnpmRoot, sharpPackage, "node_modules", "sharp"));
const { PDFDocument } = require(path.join(moduleRoot, "pdf-lib"));

function parseCsv(text) {
  const rows = [];
  let row = [], field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (ch === '"') quoted = false;
      else field += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") { row.push(field); field = ""; }
    else if (ch === "\n") {
      row.push(field.replace(/\r$/, ""));
      if (row.some(value => value.length)) rows.push(row);
      row = []; field = "";
    } else field += ch;
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }
  const header = rows.shift();
  return rows.map(values => Object.fromEntries(header.map((name, i) => [name, values[i]])));
}

function esc(value) {
  return String(value).replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;"
  })[ch]);
}

function number(value) { return Number.parseFloat(value); }
function signed(value, digits = 1) {
  const n = number(value);
  return (n >= 0 ? "+" : "") + n.toFixed(digits);
}
function scale(value, minimum, maximum, x0, x1) {
  return x0 + (value - minimum) * (x1 - x0) / (maximum - minimum);
}

async function main() {
  const [riskPath, tokenPath, outDir] = process.argv.slice(2);
  if (!riskPath || !tokenPath || !outDir) {
    throw new Error("usage: factorial_effect_figure.cjs RISK_CSV TOKEN_CSV OUT_DIR");
  }
  const risk = parseCsv(fs.readFileSync(riskPath, "utf8"));
  const tokens = parseCsv(fs.readFileSync(tokenPath, "utf8"));
  const riskBy = Object.fromEntries(risk.map(row => [row.contrast, row]));
  const tokenBy = Object.fromEntries(tokens.map(row => [row.contrast, row]));

  const series = [
    { key: "visible_test_main", label: "Average main effect", sub: "confirmatory", kind: "main" },
    { key: "test_effect__grounding_0__control_0", label: "Ungrounded · single-shot", sub: "exploratory", kind: "ungrounded" },
    { key: "test_effect__grounding_1__control_0", label: "Grounded · single-shot", sub: "exploratory", kind: "grounded" },
    { key: "test_effect__grounding_0__control_1", label: "Ungrounded · iterative", sub: "exploratory", kind: "ungrounded" },
    { key: "test_effect__grounding_1__control_1", label: "Grounded · iterative", sub: "exploratory", kind: "grounded" },
  ];

  const width = 1600, height = 900;
  const ink = "#1a1a1a", body = "#30363b", muted = "#66707a";
  const grid = "#d9dee2", zero = "#6b737b", purple = "#6f4c9b";
  const blue = "#3977a8", teal = "#2a8580", cream = "#fffaf3";
  const panelStroke = "#cfd5da";
  const riskMin = -10, riskMax = 22;
  const tokenMin = -100, tokenMax = 600;
  const left = { labelX: 80, x0: 360, x1: 760 };
  const right = { labelX: 900, x0: 1120, x1: 1510 };
  const top = 255, rowGap = 98;
  const riskTicks = [-10, 0, 10, 20];
  const tokenTicks = [-100, 0, 200, 400, 600];

  const parts = [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`,
    `<rect width="100%" height="100%" fill="#ffffff"/>`,
    `<text x="70" y="68" font-family="Arial,Helvetica,sans-serif" font-size="30" font-weight="700" fill="${ink}">Effect of visible characterization-test feedback</text>`,
    `<text x="70" y="105" font-family="Arial,Helvetica,sans-serif" font-size="17" fill="${muted}">Test ON minus test OFF · 19 independent instances · three repetitions per factorial cell</text>`,
    `<rect x="50" y="145" width="740" height="625" rx="14" fill="${cream}" stroke="${panelStroke}"/>`,
    `<rect x="820" y="145" width="730" height="625" rx="14" fill="${cream}" stroke="${panelStroke}"/>`,
    `<text x="75" y="188" font-family="Arial,Helvetica,sans-serif" font-size="19" font-weight="700" fill="${ink}">A · Strict-success risk difference</text>`,
    `<text x="845" y="188" font-family="Arial,Helvetica,sans-serif" font-size="19" font-weight="700" fill="${ink}">B · Repair-token difference</text>`,
    `<text x="75" y="217" font-family="Arial,Helvetica,sans-serif" font-size="14" fill="${muted}">build + detector resolution + private behavioral pass</text>`,
    `<text x="845" y="217" font-family="Arial,Helvetica,sans-serif" font-size="14" fill="${muted}">model input + output tokens; positive means tests cost more</text>`,
  ];

  for (const tick of riskTicks) {
    const x = scale(tick, riskMin, riskMax, left.x0, left.x1);
    parts.push(`<line x1="${x}" y1="235" x2="${x}" y2="700" stroke="${tick === 0 ? zero : grid}" stroke-width="${tick === 0 ? 2 : 1}"/>`);
    parts.push(`<text x="${x}" y="735" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="14" fill="${body}">${tick > 0 ? "+" : ""}${tick} pp</text>`);
  }
  for (const tick of tokenTicks) {
    const x = scale(tick, tokenMin, tokenMax, right.x0, right.x1);
    parts.push(`<line x1="${x}" y1="235" x2="${x}" y2="700" stroke="${tick === 0 ? zero : grid}" stroke-width="${tick === 0 ? 2 : 1}"/>`);
    parts.push(`<text x="${x}" y="735" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="14" fill="${body}">${tick > 0 ? "+" : ""}${tick}</text>`);
  }

  series.forEach((item, index) => {
    const y = top + index * rowGap;
    const color = item.kind === "main" ? purple : item.kind === "grounded" ? teal : blue;
    const rr = riskBy[item.key], tr = tokenBy[item.key];
    if (!rr || !tr) throw new Error(`missing contrast ${item.key}`);
    parts.push(`<text x="${left.labelX}" y="${y - 4}" font-family="Arial,Helvetica,sans-serif" font-size="16" font-weight="${item.kind === "main" ? 700 : 600}" fill="${ink}">${esc(item.label)}</text>`);
    parts.push(`<text x="${left.labelX}" y="${y + 19}" font-family="Arial,Helvetica,sans-serif" font-size="12" fill="${muted}">${esc(item.sub)}</text>`);
    parts.push(`<text x="${right.labelX - 55}" y="${y + 5}" font-family="Arial,Helvetica,sans-serif" font-size="15" fill="${body}">${esc(item.label.replace(" · ", " / "))}</text>`);

    const rx = scale(number(rr.estimate) * 100, riskMin, riskMax, left.x0, left.x1);
    const rlo = scale(number(rr.ci95_lo) * 100, riskMin, riskMax, left.x0, left.x1);
    const rhi = scale(number(rr.ci95_hi) * 100, riskMin, riskMax, left.x0, left.x1);
    parts.push(`<line x1="${rlo}" y1="${y}" x2="${rhi}" y2="${y}" stroke="${color}" stroke-width="4" stroke-linecap="round"/>`);
    parts.push(`<line x1="${rlo}" y1="${y - 8}" x2="${rlo}" y2="${y + 8}" stroke="${color}" stroke-width="2"/>`);
    parts.push(`<line x1="${rhi}" y1="${y - 8}" x2="${rhi}" y2="${y + 8}" stroke="${color}" stroke-width="2"/>`);
    if (item.kind === "main") parts.push(`<path d="M ${rx} ${y - 10} L ${rx + 10} ${y} L ${rx} ${y + 10} L ${rx - 10} ${y} Z" fill="${color}"/>`);
    else if (item.label.includes("iterative")) parts.push(`<rect x="${rx - 8}" y="${y - 8}" width="16" height="16" fill="${color}"/>`);
    else parts.push(`<circle cx="${rx}" cy="${y}" r="8" fill="${color}"/>`);
    parts.push(`<text x="775" y="${y + 5}" text-anchor="end" font-family="Arial,Helvetica,sans-serif" font-size="14" font-weight="600" fill="${color}">${signed(number(rr.estimate) * 100)} pp</text>`);

    const tx = scale(number(tr.estimate), tokenMin, tokenMax, right.x0, right.x1);
    const tlo = scale(number(tr.ci95_lo), tokenMin, tokenMax, right.x0, right.x1);
    const thi = scale(number(tr.ci95_hi), tokenMin, tokenMax, right.x0, right.x1);
    parts.push(`<line x1="${tlo}" y1="${y}" x2="${thi}" y2="${y}" stroke="${color}" stroke-width="4" stroke-linecap="round"/>`);
    parts.push(`<line x1="${tlo}" y1="${y - 8}" x2="${tlo}" y2="${y + 8}" stroke="${color}" stroke-width="2"/>`);
    parts.push(`<line x1="${thi}" y1="${y - 8}" x2="${thi}" y2="${y + 8}" stroke="${color}" stroke-width="2"/>`);
    if (item.kind === "main") parts.push(`<path d="M ${tx} ${y - 10} L ${tx + 10} ${y} L ${tx} ${y + 10} L ${tx - 10} ${y} Z" fill="${color}"/>`);
    else if (item.label.includes("iterative")) parts.push(`<rect x="${tx - 8}" y="${y - 8}" width="16" height="16" fill="${color}"/>`);
    else parts.push(`<circle cx="${tx}" cy="${y}" r="8" fill="${color}"/>`);
    parts.push(`<text x="1530" y="${y + 5}" text-anchor="end" font-family="Arial,Helvetica,sans-serif" font-size="14" font-weight="600" fill="${color}">${signed(tr.estimate, 0)}</text>`);
  });

  parts.push(
    `<line x1="70" y1="795" x2="1530" y2="795" stroke="${grid}"/>`,
    `<text x="70" y="828" font-family="Arial,Helvetica,sans-serif" font-size="14" fill="${body}">Marks show paired instance-level means; whiskers are 95% Student-t confidence intervals (df = 18).</text>`,
    `<text x="70" y="854" font-family="Arial,Helvetica,sans-serif" font-size="13" fill="${muted}">Only the average visible-test effect is confirmatory. Cell-specific effects are exploratory under the frozen power classification.</text>`,
    `</svg>`
  );

  fs.mkdirSync(outDir, { recursive: true });
  const base = path.join(outDir, "factorial_visible_test_effect");
  const svg = Buffer.from(parts.join("\n"), "utf8");
  fs.writeFileSync(base + ".svg", svg);
  const png = await sharp(svg, { density: 180 }).png().toBuffer();
  fs.writeFileSync(base + ".png", png);

  const pdf = await PDFDocument.create();
  const page = pdf.addPage([960, 540]);
  const image = await pdf.embedPng(png);
  page.drawImage(image, { x: 0, y: 0, width: 960, height: 540 });
  fs.writeFileSync(base + ".pdf", await pdf.save());
  process.stdout.write(`wrote ${base}.{svg,png,pdf}\n`);
}

main().catch(error => { console.error(error); process.exit(1); });
