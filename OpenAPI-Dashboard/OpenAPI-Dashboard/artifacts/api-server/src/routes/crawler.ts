import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { Router, type IRouter } from "express";

const router: IRouter = Router();

type CrawlerRun = {
  started_at: string;
  completed_at: string | null;
  exit_code: number | null;
  stdout: string;
  stderr: string;
};

let runInProgress = false;
let latestRun: CrawlerRun | null = null;

function resolveCrawlerDir() {
  const configured = process.env["CRAWLER_DIR"];
  const candidates = [
    configured,
    path.resolve(process.cwd(), "openapi-crawler"),
    path.resolve(process.cwd(), "..", "openapi-crawler"),
    path.resolve(process.cwd(), "..", "..", "openapi-crawler"),
    path.resolve(process.cwd(), "..", "..", "..", "openapi-crawler"),
  ].filter(Boolean) as string[];

  const match = candidates.find((candidate) =>
    existsSync(path.join(candidate, "main.py")),
  );

  if (!match) {
    throw new Error(
      `Could not locate openapi-crawler. Set CRAWLER_DIR to the backend folder. Checked: ${candidates.join(", ")}`,
    );
  }

  return match;
}

async function readJsonFile<T>(filePath: string, fallback: T): Promise<T> {
  try {
    const text = await readFile(filePath, "utf-8");
    return JSON.parse(text) as T;
  } catch {
    return fallback;
  }
}

async function readLogLines(filePath: string) {
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

function buildStats(catalog: any[], report: any) {
  const active = catalog.filter((entry) => entry.status === "active").length;
  const stale = catalog.filter((entry) => entry.status === "stale").length;
  const invalid = catalog.filter((entry) => entry.status === "invalid").length;

  return {
    total: catalog.length,
    active,
    stale,
    invalid,
    rejected: report?.counts?.rejected ?? 0,
  };
}

function getPythonCommand() {
  return process.env["PYTHON_BIN"] ?? (process.platform === "win32" ? "python" : "python3");
}

function startCrawlerRun(crawlerDir: string) {
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
  const catalog = await readJsonFile<any[]>(
    path.join(crawlerDir, "catalog.json"),
    [],
  );
  const report = await readJsonFile<Record<string, unknown>>(
    path.join(crawlerDir, "run_report.json"),
    {},
  );
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

router.get("/crawler/state", async (_req, res, next) => {
  try {
    res.json(await getCrawlerState());
  } catch (error) {
    next(error);
  }
});

router.post("/crawler/run", async (_req, res, next) => {
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
    next(error);
  }
});

export default router;
