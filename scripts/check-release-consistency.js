#!/usr/bin/env node

"use strict";

const fs = require("node:fs");
const path = require("node:path");

function read(root, relativePath) {
  return fs.readFileSync(path.join(root, relativePath), "utf8");
}

function uniqueMatches(source, pattern) {
  return [...new Set([...source.matchAll(pattern)].map((match) => match[1].trim()))];
}

function inspectReleaseConsistency(options = {}) {
  const root = path.resolve(options.root || path.join(__dirname, ".."));
  const strictIos = Boolean(options.strictIos);
  const errors = [];
  const warnings = [];

  const packageJson = JSON.parse(read(root, "package.json"));
  const packageLock = JSON.parse(read(root, "package-lock.json"));
  const versionSource = read(root, "web/src/version.js");
  const xcodeSource = read(root, "ios/App/App.xcodeproj/project.pbxproj");

  const currentMatch = versionSource.match(/current\s*:\s*["']([^"']+)["']/);
  const changelogMatch = versionSource.match(/changelog\s*:\s*\[\s*\{[\s\S]*?version\s*:\s*["']([^"']+)["']/);
  const marketingVersions = uniqueMatches(xcodeSource, /MARKETING_VERSION\s*=\s*([^;]+);/g);
  const buildNumbers = uniqueMatches(xcodeSource, /CURRENT_PROJECT_VERSION\s*=\s*([^;]+);/g);

  const sourceVersions = {
    package: String(packageJson.version || ""),
    lockRoot: String(packageLock.version || ""),
    lockPackage: String(packageLock.packages?.[""]?.version || ""),
    webCurrent: currentMatch?.[1] || "",
    webChangelog: changelogMatch?.[1] || "",
  };
  const sourceVersionValues = [...new Set(Object.values(sourceVersions).filter(Boolean))];

  for (const [name, value] of Object.entries(sourceVersions)) {
    if (!value) errors.push(`Missing source version: ${name}`);
  }
  if (sourceVersionValues.length !== 1) {
    errors.push(`Source versions disagree: ${JSON.stringify(sourceVersions)}`);
  }
  if (marketingVersions.length !== 1) {
    errors.push(`Xcode MARKETING_VERSION must resolve to one value; found ${marketingVersions.join(", ") || "none"}`);
  }
  if (buildNumbers.length !== 1) {
    errors.push(`Xcode CURRENT_PROJECT_VERSION must resolve to one value; found ${buildNumbers.join(", ") || "none"}`);
  }

  const sourceVersion = sourceVersionValues.length === 1 ? sourceVersionValues[0] : null;
  const iosVersion = marketingVersions.length === 1 ? marketingVersions[0] : null;
  const iosBuild = buildNumbers.length === 1 ? buildNumbers[0] : null;
  let releaseState = "unknown";

  if (sourceVersion && iosVersion) {
    if (sourceVersion === iosVersion) {
      releaseState = "aligned";
    } else if (strictIos) {
      releaseState = "blocked-for-ios-release";
      errors.push(`iOS release version ${iosVersion} does not match source version ${sourceVersion}`);
    } else {
      releaseState = "post-submission-development";
      warnings.push(
        `iOS ${iosVersion} (${iosBuild || "unknown build"}) is frozen behind source ${sourceVersion}; run with --strict-ios before packaging the next binary.`,
      );
    }
  }

  return {
    ok: errors.length === 0,
    strictIos,
    releaseState,
    sourceVersion,
    iosVersion,
    iosBuild,
    sourceVersions,
    errors,
    warnings,
  };
}

function formatReport(report) {
  const lines = [
    `Release consistency: ${report.ok ? "PASS" : "FAIL"}`,
    `- source: ${report.sourceVersion || "unresolved"}`,
    `- iOS: ${report.iosVersion || "unresolved"} (${report.iosBuild || "unresolved build"})`,
    `- state: ${report.releaseState}`,
  ];
  for (const warning of report.warnings) lines.push(`WARN ${warning}`);
  for (const error of report.errors) lines.push(`ERROR ${error}`);
  return lines.join("\n");
}

if (require.main === module) {
  const strictIos = process.argv.includes("--strict-ios");
  const asJson = process.argv.includes("--json");
  const report = inspectReleaseConsistency({ strictIos });
  process.stdout.write(`${asJson ? JSON.stringify(report, null, 2) : formatReport(report)}\n`);
  if (!report.ok) process.exitCode = 1;
}

module.exports = { formatReport, inspectReleaseConsistency };
