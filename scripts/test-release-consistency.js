#!/usr/bin/env node

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { inspectReleaseConsistency } = require("./check-release-consistency.js");

function fixture({ source = "1.0.27", lock = source, web = source, changelog = web, ios = source, builds = ["34", "34"] } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "munea-release-consistency-"));
  fs.mkdirSync(path.join(root, "web/src"), { recursive: true });
  fs.mkdirSync(path.join(root, "ios/App/App.xcodeproj"), { recursive: true });
  fs.writeFileSync(path.join(root, "package.json"), JSON.stringify({ version: source }));
  fs.writeFileSync(path.join(root, "package-lock.json"), JSON.stringify({ version: lock, packages: { "": { version: lock } } }));
  fs.writeFileSync(
    path.join(root, "web/src/version.js"),
    `window.MuneaVersion = { current: '${web}', changelog: [{ version: '${changelog}' }] };`,
  );
  fs.writeFileSync(
    path.join(root, "ios/App/App.xcodeproj/project.pbxproj"),
    `MARKETING_VERSION = ${ios}; CURRENT_PROJECT_VERSION = ${builds[0]};\n` +
      `MARKETING_VERSION = ${ios}; CURRENT_PROJECT_VERSION = ${builds[1]};\n`,
  );
  return root;
}

function runCase(name, fn) {
  const root = fn();
  fs.rmSync(root, { recursive: true, force: true });
  process.stdout.write(`PASS ${name}\n`);
}

runCase("aligned source and iOS metadata pass strict mode", () => {
  const root = fixture();
  const report = inspectReleaseConsistency({ root, strictIos: true });
  assert.equal(report.ok, true);
  assert.equal(report.releaseState, "aligned");
  assert.equal(report.sourceVersion, "1.0.27");
  assert.equal(report.iosVersion, "1.0.27");
  assert.equal(report.iosBuild, "34");
  return root;
});

runCase("post-submission source can advance without changing the frozen iOS binary", () => {
  const root = fixture({ source: "1.0.27", ios: "1.0.26", builds: ["33", "33"] });
  const report = inspectReleaseConsistency({ root });
  assert.equal(report.ok, true);
  assert.equal(report.releaseState, "post-submission-development");
  assert.equal(report.warnings.length, 1);
  return root;
});

runCase("strict iOS packaging blocks version drift", () => {
  const root = fixture({ source: "1.0.27", ios: "1.0.26", builds: ["33", "33"] });
  const report = inspectReleaseConsistency({ root, strictIos: true });
  assert.equal(report.ok, false);
  assert.equal(report.releaseState, "blocked-for-ios-release");
  return root;
});

runCase("package lock drift fails", () => {
  const root = fixture({ lock: "1.0.26" });
  const report = inspectReleaseConsistency({ root });
  assert.equal(report.ok, false);
  assert.match(report.errors.join("\n"), /Source versions disagree/);
  return root;
});

runCase("web changelog head drift fails", () => {
  const root = fixture({ changelog: "1.0.26" });
  const report = inspectReleaseConsistency({ root });
  assert.equal(report.ok, false);
  assert.match(report.errors.join("\n"), /Source versions disagree/);
  return root;
});

runCase("Xcode build configurations must agree", () => {
  const root = fixture({ builds: ["33", "34"] });
  const report = inspectReleaseConsistency({ root });
  assert.equal(report.ok, false);
  assert.match(report.errors.join("\n"), /CURRENT_PROJECT_VERSION/);
  return root;
});
