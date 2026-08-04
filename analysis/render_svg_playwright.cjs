#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

async function main() {
  if (process.argv.length !== 3) {
    throw new Error("usage: render_svg_playwright.cjs <figure.svg>");
  }
  const svgPath = path.resolve(process.argv[2]);
  const base = svgPath.slice(0, -path.extname(svgPath).length);
  const svg = fs.readFileSync(svgPath, "utf8");
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1120, height: 620 } });
    await page.setContent(
      `<style>html,body{margin:0;width:1120px;height:620px;overflow:hidden}</style>${svg}`,
      { waitUntil: "load" },
    );
    await page.screenshot({
      path: `${base}.png`,
      type: "png",
      clip: { x: 0, y: 0, width: 1120, height: 620 },
      scale: "css",
    });
    await page.pdf({
      path: `${base}.pdf`,
      width: "11.2in",
      height: "6.2in",
      printBackground: true,
      margin: { top: 0, right: 0, bottom: 0, left: 0 },
    });
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify({
    svg: svgPath,
    png: `${base}.png`,
    pdf: `${base}.pdf`,
  }) + "\n");
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
