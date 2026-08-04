#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

async function main() {
  if (process.argv.length !== 4) {
    throw new Error("usage: render_svg_variants.cjs <figure.svg> <node_modules>");
  }
  const moduleRoot = path.resolve(process.argv[3]);
  const sharp = require(path.join(moduleRoot, "sharp"));
  const { PDFDocument } = require(path.join(moduleRoot, "pdf-lib"));
  const svgPath = path.resolve(process.argv[2]);
  if (path.extname(svgPath).toLowerCase() !== ".svg") {
    throw new Error("input must be an SVG");
  }
  const base = svgPath.slice(0, -4);
  const source = fs.readFileSync(svgPath);
  const png = await sharp(source, { density: 300 }).png().toBuffer();
  fs.writeFileSync(`${base}.png`, png);

  const metadata = await sharp(png).metadata();
  const width = metadata.width;
  const height = metadata.height;
  if (!width || !height) {
    throw new Error("rendered PNG has invalid dimensions");
  }
  const pageWidth = 806.4;
  const pageHeight = pageWidth * height / width;
  const document = await PDFDocument.create();
  const page = document.addPage([pageWidth, pageHeight]);
  const embedded = await document.embedPng(png);
  page.drawImage(embedded, { x: 0, y: 0, width: pageWidth, height: pageHeight });
  fs.writeFileSync(`${base}.pdf`, await document.save());
  process.stdout.write(JSON.stringify({
    svg: svgPath,
    png: `${base}.png`,
    pdf: `${base}.pdf`,
    pixel_width: width,
    pixel_height: height,
  }) + "\n");
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
