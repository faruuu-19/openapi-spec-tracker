import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import cors from "cors";
import express from "express";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const port = Number(process.env.PORT ?? 3001);
let runInProgress = false;
let latestRun = null;

app.use(cors());
app.use(express.json());

function resolveCrawlerDir() {
  const configured = process.env.CRAWLER_DIR;
  const candidates = [
    configured,
    path.resolve(dirname, "..", "..", "..", "..", "openapi-crawler"),
    path.resolve(process.cwd(), "..", "..", "openapi-crawler"),
    path.resolve(process.cwd(), "..", "..", "..", "openapi-crawler"),
  ].filter(Boolean);

  const match = candidates.find((candidate) => existsSync(path.join(candidate, "main.py")));
  if (!match) {
    throw new Error(`Could not locate openapi-crawler. Set CRAWLER_DIR. Checked: ${candidates.join(", ")}`);
  }
  return match;
}

async function readJsonFile(filePath, fallback) {
  try {
    return JSON.parse(await readFile(filePath, "utf-8"));
  } catch {
    return fallback;
  }
}

async function readLogLines(filePath) {
  try {
    const text = await readFile(filePath, "utf-8");
    return text
      .split(/\r?\n/)
      .filter(Boolean)
      .slice(-200)
      .map((line) => {
        try {
          return JSON.parse(line);
        } catch {
          return { level: "info", message: line };
        }
      });
  } catch {
    return [];
  }
}

function buildStats(catalog, report) {
  return {
    total: catalog.length,
    active: catalog.filter((entry) => entry.status === "active").length,
    stale: catalog.filter((entry) => entry.status === "stale").length,
    invalid: catalog.filter((entry) => entry.status === "invalid").length,
    rejected: report?.counts?.rejected ?? 0,
  };
}

function getPythonCommand() {
  return process.env.PYTHON_BIN ?? (process.platform === "win32" ? "python" : "python3");
}

function startCrawlerRun(crawlerDir) {
  runInProgress = true;
  latestRun = {
    started_at: new Date().toISOString(),
    completed_at: null,
    exit_code: null,
    stdout: "",
    stderr: "",
  };

  const child = spawn(getPythonCommand(), ["main.py"], {
    cwd: crawlerDir,
    shell: process.platform === "win32",
    env: process.env,
  });

  child.stdout.on("data", (chunk) => {
    if (latestRun) latestRun.stdout += chunk.toString();
  });

  child.stderr.on("data", (chunk) => {
    if (latestRun) latestRun.stderr += chunk.toString();
  });

  child.on("error", (error) => {
    if (latestRun) {
      latestRun.completed_at = new Date().toISOString();
      latestRun.exit_code = 1;
      latestRun.stderr += `${latestRun.stderr ? "\n" : ""}${error.message}`;
    }
    runInProgress = false;
  });

  child.on("close", (exitCode) => {
    if (latestRun) {
      latestRun.completed_at = new Date().toISOString();
      latestRun.exit_code = exitCode;
    }
    runInProgress = false;
  });
}

async function getCrawlerState() {
  const crawlerDir = resolveCrawlerDir();
  const catalog = await readJsonFile(path.join(crawlerDir, "catalog.json"), []);
  const report = await readJsonFile(path.join(crawlerDir, "run_report.json"), {});
  const logs = await readLogLines(path.join(crawlerDir, "logs", "crawler.log"));

  return {
    crawler_dir: crawlerDir,
    catalog,
    report,
    logs,
    stats: buildStats(catalog, report),
    running: runInProgress,
    run: latestRun,
  };
}

app.get("/api/healthz", (_req, res) => {
  res.json({ status: "ok" });
});

app.get("/api/crawler/state", async (_req, res) => {
  try {
    res.json(await getCrawlerState());
  } catch (error) {
    res.status(500).json({ error: error instanceof Error ? error.message : "Unable to read crawler state" });
  }
});

app.post("/api/crawler/run", async (_req, res) => {
  if (runInProgress) {
    res.status(409).json({ error: "Crawler run already in progress" });
    return;
  }

  try {
    const crawlerDir = resolveCrawlerDir();
    startCrawlerRun(crawlerDir);
    res.status(202).json(await getCrawlerState());
  } catch (error) {
    runInProgress = false;
    res.status(500).json({ error: error instanceof Error ? error.message : "Crawler run failed" });
  }
});

app.listen(port, () => {
  console.log(`Crawler API listening on http://localhost:${port}`);
});
