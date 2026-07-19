import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const DEFAULT_WINDOW_MS = 7 * 24 * 60 * 60 * 1000;
const DEFAULT_INTERVAL_MINUTES = 5;

function percentage(numerator, denominator) {
  if (!denominator) return null;
  return Number(((numerator / denominator) * 100).toFixed(3));
}

function runTimestamp(run) {
  return run.run_started_at || run.created_at || null;
}

export function buildSevenDayReport(
  workflowRuns,
  {
    from,
    to,
    intervalMinutes = DEFAULT_INTERVAL_MINUTES,
    repository = null,
    sourceWorkflow = "service-watchdog.yml",
  },
) {
  const fromMs = new Date(from).getTime();
  const toMs = new Date(to).getTime();
  const intervalMs = intervalMinutes * 60 * 1000;

  if (!Number.isFinite(fromMs) || !Number.isFinite(toMs) || toMs <= fromMs) {
    throw new Error("SLO report requires a valid half-open time window [from, to)");
  }
  if (!Number.isFinite(intervalMs) || intervalMs <= 0) {
    throw new Error("intervalMinutes must be greater than zero");
  }

  const scheduled = workflowRuns.filter((run) => {
    if (run.event !== "schedule") return false;
    const timestamp = new Date(runTimestamp(run)).getTime();
    return Number.isFinite(timestamp) && timestamp >= fromMs && timestamp < toMs;
  });
  const completed = scheduled.filter((run) => run.status === "completed");
  const successful = completed.filter((run) => run.conclusion === "success");
  const expectedSlots = Math.floor((toMs - fromMs) / intervalMs);
  const completedSlots = completed.length;
  const successfulSlots = successful.length;
  const unavailableSlots = Math.max(0, expectedSlots - successfulSlots);
  const missingSlots = Math.max(0, expectedSlots - completedSlots);
  const windowHours = Number(((toMs - fromMs) / (60 * 60 * 1000)).toFixed(3));
  const coveragePct = Math.min(100, percentage(completedSlots, expectedSlots) ?? 0);

  return {
    schema: "munea.service-slo.report.v1",
    generatedAt: new Date().toISOString(),
    evidenceType: "synthetic-control-plane",
    repository,
    sourceWorkflow,
    window: {
      semantics: "half-open-[from,to)",
      from: new Date(fromMs).toISOString(),
      to: new Date(toMs).toISOString(),
      hours: windowHours,
      intervalMinutes,
    },
    denominator: {
      definition: "expected 5-minute scheduled workflow slots in the report window",
      expectedSlots,
      completedScheduledSlots: completedSlots,
      missingScheduledSlots: missingSlots,
    },
    metrics: {
      successfulSlots,
      unsuccessfulOrMissingSlots: unavailableSlots,
      coveragePct,
      observedSuccessPct: percentage(successfulSlots, completedSlots),
      conservativeAvailabilityPct: percentage(Math.min(successfulSlots, expectedSlots), expectedSlots),
      conservativeUnavailablePct: percentage(unavailableSlots, expectedSlots),
    },
    evidenceReady: windowHours >= 168 && coveragePct >= 95,
    limitations: [
      "Measures scheduled synthetic control-plane checks, not real user call success or end-to-end App quality.",
      "Missing scheduled runs count against conservative availability.",
      "Latency is recorded in daily watchdog snapshots and is not claimed as production traffic p95.",
    ],
  };
}

export async function fetchWorkflowRuns({ repository, token, workflow, from }) {
  if (!repository || !token) throw new Error("GITHUB_REPOSITORY and GITHUB_TOKEN are required");

  const runs = [];
  for (let page = 1; page <= 30; page += 1) {
    const query = new URLSearchParams({
      per_page: "100",
      page: String(page),
      event: "schedule",
      created: `>=${from}`,
    });
    const url = `https://api.github.com/repos/${repository}/actions/workflows/${workflow}/runs?${query}`;
    const response = await fetch(url, {
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "munea-service-slo-report",
      },
    });
    if (!response.ok) {
      throw new Error(`GitHub workflow runs API returned HTTP ${response.status}: ${(await response.text()).slice(0, 240)}`);
    }
    const payload = await response.json();
    const pageRuns = Array.isArray(payload.workflow_runs) ? payload.workflow_runs : [];
    runs.push(...pageRuns);
    if (pageRuns.length < 100) break;
  }
  return runs;
}

function readOption(flag) {
  const index = process.argv.indexOf(flag);
  if (index === -1) return null;
  const value = process.argv[index + 1];
  if (!value || value.startsWith("--")) throw new Error(`${flag} requires a value`);
  return value;
}

async function writeReport(outputPath, report) {
  const absolutePath = resolve(outputPath);
  await mkdir(dirname(absolutePath), { recursive: true });
  await writeFile(absolutePath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return absolutePath;
}

export async function main() {
  const repository = process.env.GITHUB_REPOSITORY || readOption("--repository");
  const token = process.env.GITHUB_TOKEN;
  const workflow = readOption("--workflow") || "service-watchdog.yml";
  const output = readOption("--output") || "dist/service-slo/rolling-7d.json";
  const fixture = readOption("--fixture");
  const to = new Date(readOption("--to") || Date.now());
  const from = new Date(readOption("--from") || to.getTime() - DEFAULT_WINDOW_MS);

  let workflowRuns;
  if (fixture) {
    const payload = JSON.parse(await readFile(resolve(fixture), "utf8"));
    workflowRuns = Array.isArray(payload) ? payload : payload.workflow_runs;
    if (!Array.isArray(workflowRuns)) throw new Error("Fixture must be an array or contain workflow_runs[]");
  } else {
    workflowRuns = await fetchWorkflowRuns({
      repository,
      token,
      workflow,
      from: from.toISOString(),
    });
  }

  const report = buildSevenDayReport(workflowRuns, {
    from,
    to,
    repository,
    sourceWorkflow: workflow,
  });
  const outputPath = await writeReport(output, report);
  console.log(`SLO_REPORT ${outputPath}`);
  console.log(JSON.stringify(report.metrics));

  if (process.env.GITHUB_STEP_SUMMARY) {
    const summary = [
      "## Service SLO evidence",
      "",
      `- Window: ${report.window.from} → ${report.window.to}`,
      `- Scheduled coverage: ${report.metrics.coveragePct}% (${report.denominator.completedScheduledSlots}/${report.denominator.expectedSlots})`,
      `- Observed success: ${report.metrics.observedSuccessPct ?? "n/a"}%`,
      `- Conservative availability: ${report.metrics.conservativeAvailabilityPct}%`,
      `- Evidence ready: ${report.evidenceReady ? "yes" : "no"}`,
      "",
      "> Synthetic control-plane evidence only; this does not prove App login, purchase, credits, or call E2E.",
      "",
    ].join("\n");
    await appendFile(process.env.GITHUB_STEP_SUMMARY, summary, "utf8");
  }
}

const invokedDirectly = process.argv[1] && import.meta.url.endsWith(process.argv[1].replace(/\\/g, "/").split("/").pop());
if (invokedDirectly) {
  await main();
}
