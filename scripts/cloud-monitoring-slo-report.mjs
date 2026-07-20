import { spawnSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_WINDOW_MS = 7 * 24 * 60 * 60 * 1000;
const METRIC_TYPE = "monitoring.googleapis.com/uptime_check/check_passed";

function percentage(numerator, denominator) {
  if (!denominator) return null;
  return Number(((numerator / denominator) * 100).toFixed(3));
}

function normalizedRegion(value) {
  const normalized = String(value || "").trim().toLowerCase().replaceAll("_", "-");
  if (normalized === "asia-pacific" || normalized.startsWith("apac-")) return "asia-pacific";
  if (normalized === "europe" || normalized.startsWith("eur-")) return "europe";
  return normalized;
}

function boolValue(value) {
  if (value === true || value === "true") return true;
  if (value === false || value === "false") return false;
  return null;
}

function checkIdFromName(name) {
  return String(name || "").split("/").filter(Boolean).at(-1) || null;
}

function targetSummary(target, expectedSlots, regionCount, samples) {
  const expectedRegionalSamples = expectedSlots * regionCount;
  const passedSamples = samples.filter((sample) => sample.passed).length;
  const failedSamples = samples.length - passedSamples;
  const missingSamples = Math.max(0, expectedRegionalSamples - samples.length);
  return {
    targetId: target.id,
    environment: target.environment,
    expectedRegionalSamples,
    observedUniqueSamples: samples.length,
    passedSamples,
    failedSamples,
    missingSamples,
    coveragePct: Math.min(100, percentage(samples.length, expectedRegionalSamples) ?? 0),
    observedPassPct: percentage(passedSamples, samples.length),
    conservativeAvailabilityPct: percentage(Math.min(passedSamples, expectedRegionalSamples), expectedRegionalSamples),
  };
}

export function buildCloudMonitoringReport(
  { configs = [], timeSeries = [] },
  { manifest, from, to },
) {
  const fromMs = new Date(from).getTime();
  const toMs = new Date(to).getTime();
  const intervalMinutes = Number(manifest?.periodMinutes);
  const intervalMs = intervalMinutes * 60 * 1000;
  if (!Number.isFinite(fromMs) || !Number.isFinite(toMs) || toMs <= fromMs) {
    throw new Error("Cloud Monitoring report requires a valid half-open time window [from, to)");
  }
  if (!Number.isFinite(intervalMs) || intervalMs <= 0) {
    throw new Error("manifest.periodMinutes must be greater than zero");
  }
  if (!Array.isArray(manifest?.targets) || !manifest.targets.length || !Array.isArray(manifest?.regions) || !manifest.regions.length) {
    throw new Error("manifest must contain non-empty targets[] and regions[]");
  }

  const targetIds = new Set(manifest.targets.map((target) => target.id));
  const expectedRegions = new Set(manifest.regions.map(normalizedRegion));
  const configsByTarget = new Map();
  const checkToTarget = new Map();
  for (const config of configs) {
    if (config?.userLabels?.managed_by !== "munea_repo" || config?.userLabels?.component !== "service_slo") continue;
    const targetId = config?.userLabels?.target_id;
    const checkId = checkIdFromName(config?.name);
    if (!targetIds.has(targetId) || !checkId) continue;
    const current = configsByTarget.get(targetId) || [];
    current.push(checkId);
    configsByTarget.set(targetId, current);
    checkToTarget.set(checkId, targetId);
  }

  const samples = [];
  const seen = new Set();
  let duplicatePoints = 0;
  let invalidPoints = 0;
  let unknownCheckIdPoints = 0;
  let unexpectedRegionPoints = 0;
  const unexpectedRegions = new Map();

  for (const series of timeSeries) {
    const labels = series?.metric?.labels || {};
    const checkId = labels.check_id;
    const region = normalizedRegion(labels.checker_location);
    const targetId = checkToTarget.get(checkId);
    for (const point of Array.isArray(series?.points) ? series.points : []) {
      if (!targetId) {
        unknownCheckIdPoints += 1;
        continue;
      }
      if (!expectedRegions.has(region)) {
        unexpectedRegionPoints += 1;
        unexpectedRegions.set(region || "(missing)", (unexpectedRegions.get(region || "(missing)") || 0) + 1);
        continue;
      }
      const timestamp = new Date(point?.interval?.endTime).getTime();
      const passed = boolValue(point?.value?.boolValue);
      if (!Number.isFinite(timestamp) || timestamp < fromMs || timestamp >= toMs || passed === null) {
        invalidPoints += 1;
        continue;
      }
      const key = `${checkId}|${region}|${timestamp}`;
      if (seen.has(key)) {
        duplicatePoints += 1;
        continue;
      }
      seen.add(key);
      samples.push({ targetId, passed });
    }
  }

  const expectedSlotsPerRegion = Math.floor((toMs - fromMs) / intervalMs);
  const expectedRegionalSamples = expectedSlotsPerRegion * manifest.targets.length * expectedRegions.size;
  const passedSamples = samples.filter((sample) => sample.passed).length;
  const failedSamples = samples.length - passedSamples;
  const missingSamples = Math.max(0, expectedRegionalSamples - samples.length);
  const windowHours = Number(((toMs - fromMs) / (60 * 60 * 1000)).toFixed(3));
  const coveragePct = Math.min(100, percentage(samples.length, expectedRegionalSamples) ?? 0);
  const missingConfigTargets = manifest.targets.filter((target) => !configsByTarget.has(target.id)).map((target) => target.id);
  const duplicateConfigTargets = [...configsByTarget.entries()].filter(([, ids]) => ids.length > 1).map(([targetId]) => targetId);

  return {
    schema: "munea.cloud-monitoring.slo-report.v1",
    generatedAt: new Date().toISOString(),
    evidenceType: "cloud-monitoring-regional-uptime",
    sourceMetric: METRIC_TYPE,
    project: manifest.project,
    window: {
      semantics: "half-open-[from,to)",
      from: new Date(fromMs).toISOString(),
      to: new Date(toMs).toISOString(),
      hours: windowHours,
      intervalMinutes,
    },
    configuration: {
      manifestTargetCount: manifest.targets.length,
      mappedTargetCount: manifest.targets.length - missingConfigTargets.length,
      regionCount: expectedRegions.size,
      missingConfigTargets,
      duplicateConfigTargets,
    },
    denominator: {
      definition: "manifest targets x configured checker regions x expected probe slots",
      expectedSlotsPerRegion,
      expectedRegionalSamples,
      observedUniqueSamples: samples.length,
      missingSamples,
    },
    metrics: {
      passedSamples,
      failedSamples,
      unavailableOrMissingSamples: failedSamples + missingSamples,
      coveragePct,
      observedPassPct: percentage(passedSamples, samples.length),
      conservativeAvailabilityPct: percentage(Math.min(passedSamples, expectedRegionalSamples), expectedRegionalSamples),
    },
    dataQuality: {
      duplicatePointsIgnored: duplicatePoints,
      invalidOrOutOfWindowPointsIgnored: invalidPoints,
      unknownCheckIdPointsIgnored: unknownCheckIdPoints,
      unexpectedRegionPointsIgnored: unexpectedRegionPoints,
      unexpectedRegions: Object.fromEntries([...unexpectedRegions.entries()].sort(([left], [right]) => left.localeCompare(right))),
    },
    perTarget: manifest.targets.map((target) => targetSummary(
      target,
      expectedSlotsPerRegion,
      expectedRegions.size,
      samples.filter((sample) => sample.targetId === target.id),
    )),
    evidenceReady: windowHours >= 168
      && coveragePct >= 95
      && missingConfigTargets.length === 0
      && duplicateConfigTargets.length === 0,
    limitations: [
      "Measures regional synthetic HTTP uptime, not real-user App login, purchase, credits, or call E2E.",
      "Missing regional samples count against conservative availability.",
      "This report does not change Cloud Monitoring, IAM, deployments, databases, or runtime configuration.",
    ],
  };
}

function readOption(flag) {
  const index = process.argv.indexOf(flag);
  if (index === -1) return null;
  const value = process.argv[index + 1];
  if (!value || value.startsWith("--")) throw new Error(`${flag} requires a value`);
  return value;
}

function accessTokenFromGcloud() {
  const command = process.platform === "win32" ? (process.env.ComSpec || "cmd.exe") : "gcloud";
  const args = process.platform === "win32"
    ? ["/d", "/s", "/c", "gcloud.cmd auth print-access-token"]
    : ["auth", "print-access-token"];
  const result = spawnSync(command, args, {
    encoding: "utf8",
    windowsHide: true,
  });
  if (result.status !== 0) {
    const detail = result.error?.message || String(result.stderr || "").trim() || `exit ${result.status}`;
    throw new Error(`Unable to obtain a Google access token from gcloud: ${detail.slice(0, 240)}`);
  }
  const token = String(result.stdout || "").trim();
  if (!token) throw new Error("gcloud returned an empty access token");
  return token;
}

async function fetchJson(url, token) {
  const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) {
    throw new Error(`Cloud Monitoring API returned HTTP ${response.status}: ${(await response.text()).slice(0, 240)}`);
  }
  return response.json();
}

export async function fetchUptimeConfigs({ project, token }) {
  const configs = [];
  let pageToken = null;
  do {
    const query = new URLSearchParams({ pageSize: "1000" });
    if (pageToken) query.set("pageToken", pageToken);
    const url = `https://monitoring.googleapis.com/v3/projects/${encodeURIComponent(project)}/uptimeCheckConfigs?${query}`;
    const payload = await fetchJson(url, token);
    configs.push(...(Array.isArray(payload.uptimeCheckConfigs) ? payload.uptimeCheckConfigs : []));
    pageToken = payload.nextPageToken || null;
  } while (pageToken);
  return configs;
}

function escapedFilterValue(value) {
  return String(value).replaceAll("\\", "\\\\").replaceAll('"', '\\"');
}

export async function fetchCheckPassedSeries({ project, token, checkIds, from, to }) {
  if (!checkIds.length) return [];
  const checkFilter = checkIds.map((id) => `metric.labels.check_id = "${escapedFilterValue(id)}"`).join(" OR ");
  const filter = `metric.type = "${METRIC_TYPE}" AND (${checkFilter})`;
  const timeSeries = [];
  let pageToken = null;
  do {
    const query = new URLSearchParams({
      filter,
      "interval.startTime": new Date(from).toISOString(),
      "interval.endTime": new Date(to).toISOString(),
      view: "FULL",
      pageSize: "100000",
    });
    if (pageToken) query.set("pageToken", pageToken);
    const url = `https://monitoring.googleapis.com/v3/projects/${encodeURIComponent(project)}/timeSeries?${query}`;
    const payload = await fetchJson(url, token);
    timeSeries.push(...(Array.isArray(payload.timeSeries) ? payload.timeSeries : []));
    pageToken = payload.nextPageToken || null;
  } while (pageToken);
  return timeSeries;
}

async function writeReport(outputPath, report) {
  const absolutePath = resolve(outputPath);
  await mkdir(dirname(absolutePath), { recursive: true });
  await writeFile(absolutePath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return absolutePath;
}

export async function main() {
  const manifestPath = resolve(readOption("--manifest") || "deploy/monitoring/uptime-checks.json");
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  const output = readOption("--output") || "dist/service-slo/cloud-monitoring-rolling-7d.json";
  const fixturePath = readOption("--fixture");
  const to = new Date(readOption("--to") || Date.now());
  const from = new Date(readOption("--from") || to.getTime() - DEFAULT_WINDOW_MS);

  let configs;
  let timeSeries;
  if (fixturePath) {
    const fixture = JSON.parse(await readFile(resolve(fixturePath), "utf8"));
    configs = fixture.configs;
    timeSeries = fixture.timeSeries;
  } else {
    const token = accessTokenFromGcloud();
    configs = await fetchUptimeConfigs({ project: manifest.project, token });
    const managedCheckIds = configs
      .filter((config) => config?.userLabels?.managed_by === "munea_repo" && config?.userLabels?.component === "service_slo")
      .map((config) => checkIdFromName(config.name))
      .filter(Boolean);
    timeSeries = await fetchCheckPassedSeries({
      project: manifest.project,
      token,
      checkIds: managedCheckIds,
      from,
      to,
    });
  }

  const report = buildCloudMonitoringReport({ configs, timeSeries }, { manifest, from, to });
  const outputPath = await writeReport(output, report);
  console.log(`CLOUD_MONITORING_SLO_REPORT ${outputPath}`);
  console.log(JSON.stringify({
    metrics: report.metrics,
    dataQuality: report.dataQuality,
    evidenceReady: report.evidenceReady,
  }));
}

const invokedDirectly = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (invokedDirectly) {
  await main();
}
