#!/usr/bin/env node
/** Export the annual SVG to a one-page vector PDF using Playwright/Chromium. */
const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require('playwright');

const source = path.resolve(process.argv[2] || 'analysis/jsonnet_evolution/figures/jsonnet_annual_timeline.svg');
const output = path.resolve(process.argv[3] || 'analysis/jsonnet_evolution/figures/jsonnet_annual_timeline.pdf');
const executablePath = process.env.BROWSER_EXECUTABLE;
(async () => {
  const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  const uri = pathToFileURL(source).href;
  await page.setContent(`<!doctype html><style>@page{size:1600px 900px;margin:0}html,body{width:1600px;height:900px;margin:0;overflow:hidden}img{display:block;width:1600px;height:900px}</style><img src="${uri}">`, { waitUntil: 'networkidle' });
  await page.pdf({ path: output, width: '1600px', height: '900px', margin: { top: 0, right: 0, bottom: 0, left: 0 }, printBackground: true, preferCSSPageSize: true });
  await browser.close();
  console.log(output);
})().catch(error => { console.error(error); process.exit(1); });
