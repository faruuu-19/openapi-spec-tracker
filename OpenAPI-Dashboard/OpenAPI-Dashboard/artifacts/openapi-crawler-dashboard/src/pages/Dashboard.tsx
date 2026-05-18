import React, { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  Archive,
  BarChart2,
  CheckCircle2,
  Clock,
  Copy,
  Database,
  Diff,
  ExternalLink,
  FileCode,
  FileJson,
  FileText,
  GitBranch,
  GitCompare,
  Hash,
  Info,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

type Status = "active" | "stale" | "invalid" | string;

type CatalogHistory = {
  version?: string;
  replaced_by_version?: string;
  semantic_hash?: string;
  content_hash?: string;
  paths_count?: number;
  recorded_at?: string;
  paths_delta?: number;
  diff?: {
    added_paths?: string[];
    removed_paths?: string[];
    added_count?: number;
    removed_count?: number;
    net_paths_delta?: number;
  };
};

type CatalogEntry = {
  id: string;
  source_url: string;
  sources?: string[];
  source_count?: number;
  title?: string;
  oas_version?: string;
  latest_version?: string;
  paths_count?: number;
  path_keys?: string[];
  servers?: string[];
  tags?: string[];
  description?: string;
  fetched_at?: string;
  last_checked_at?: string;
  status?: Status;
  hash?: string;
  semantic_hash?: string;
  content_hash?: string;
  confidence_score?: number;
  validation_notes?: string[];
  failure_count?: number;
  stale_reason?: string;
  last_error?: string;
  history?: CatalogHistory[];
};

type CrawlerState = {
  crawler_dir?: string;
  catalog: CatalogEntry[];
  report: any;
  logs: any[];
  stats: {
    total: number;
    active: number;
    stale: number;
    invalid: number;
    rejected: number;
  };
  running?: boolean;
  run?: {
    started_at: string;
    completed_at: string | null;
    exit_code: number | null;
    stdout: string;
    stderr: string;
  };
};

type UiEntry = {
  raw: CatalogEntry;
  id: string;
  title: string;
  status: Status;
  oasVersion: string;
  latestVersion: string;
  paths: number;
  confidence: number;
  sourceUrls: string[];
  sourceCount: number;
  lastFetched: string;
  validationNotes: string[];
  history: Array<{
    version: string;
    replacedBy?: string;
    date: string;
    hash: string;
    delta: number;
    added: string[];
    removed: string[];
  }>;
  diffAdded: string[];
  diffRemoved: string[];
};

const emptyState: CrawlerState = {
  catalog: [],
  report: {},
  logs: [],
  stats: {
    total: 0,
    active: 0,
    stale: 0,
    invalid: 0,
    rejected: 0,
  },
};

async function fetchCrawlerState(): Promise<CrawlerState> {
  const response = await fetch("/api/crawler/state");
  if (!response.ok) {
    throw new Error(`Unable to load crawler state (${response.status})`);
  }
  return response.json();
}

async function runCrawler(): Promise<CrawlerState> {
  const response = await fetch("/api/crawler/run", { method: "POST" });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.error ?? `Crawler run failed (${response.status})`);
  }
  return body;
}

function formatDate(value?: string) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function truncateHash(value?: string, length = 8) {
  return value ? value.slice(0, length) : "unknown";
}

function normalizeConfidence(value?: number) {
  if (typeof value !== "number" || Number.isNaN(value)) return 0;
  return Math.round(value <= 1 ? value * 100 : value);
}

function deltaLabel(delta: number) {
  if (delta > 0) return `+${delta} paths`;
  if (delta < 0) return `${delta} paths`;
  return "0 paths";
}

function toUiEntry(entry: CatalogEntry): UiEntry {
  const history = [...(entry.history ?? [])].reverse().map((item) => ({
    version: item.version ?? "unknown",
    replacedBy: item.replaced_by_version,
    date: formatDate(item.recorded_at),
    hash: truncateHash(item.semantic_hash ?? item.content_hash),
    delta: item.paths_delta ?? item.diff?.net_paths_delta ?? 0,
    added: item.diff?.added_paths ?? [],
    removed: item.diff?.removed_paths ?? [],
  }));
  const latestHistory = history[0];

  return {
    raw: entry,
    id: entry.id,
    title: entry.title ?? entry.id,
    status: entry.status ?? "active",
    oasVersion: entry.oas_version ?? "unknown",
    latestVersion: entry.latest_version ?? "unknown",
    paths: entry.paths_count ?? entry.path_keys?.length ?? 0,
    confidence: normalizeConfidence(entry.confidence_score),
    sourceUrls: entry.sources?.length ? entry.sources : [entry.source_url].filter(Boolean),
    sourceCount: entry.source_count ?? entry.sources?.length ?? 1,
    lastFetched: formatDate(entry.last_checked_at ?? entry.fetched_at),
    validationNotes: entry.validation_notes ?? [],
    history,
    diffAdded: latestHistory?.added ?? [],
    diffRemoved: latestHistory?.removed ?? [],
  };
}

function logTimestamp(log: any) {
  return log.timestamp ?? log.ts ?? "";
}

function logMessage(log: any) {
  return log.message ?? log.msg ?? JSON.stringify(log);
}

function reportCounts(report: any) {
  return report?.counts ?? {};
}

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState("catalog");
  const [state, setState] = useState<CrawlerState>(emptyState);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const crawlerRunning = running || Boolean(state.running);

  const loadState = async () => {
    try {
      setError(null);
      const next = await fetchCrawlerState();
      setState(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load crawler state");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadState();
    const interval = window.setInterval(loadState, crawlerRunning ? 2000 : 7000);
    return () => window.clearInterval(interval);
  }, [crawlerRunning]);

  const handleRunCrawler = async () => {
    if (crawlerRunning) return;
    setRunning(true);
    setError(null);
    try {
      const next = await runCrawler();
      setState(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Crawler run failed");
      await loadState();
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="min-h-[100dvh] bg-background text-foreground font-sans">
      <header className="border-b border-border/40 bg-card py-4 px-6 md:px-8 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded bg-primary text-primary-foreground flex items-center justify-center font-bold font-mono">
            <Search size={18} />
          </div>
          <div>
            <h1 className="text-lg font-semibold leading-tight tracking-tight text-foreground">OAS Crawler</h1>
            <p className="text-xs text-muted-foreground font-mono">
              {state.crawler_dir ? "connected to openapi-crawler" : "waiting for backend connection"}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {error && (
            <span className="max-w-md truncate rounded border border-[#ef4444]/20 bg-[#ef4444]/10 px-3 py-1.5 text-xs text-[#b91c1c]">
              {error}
            </span>
          )}
          <Button variant="outline" onClick={loadState} disabled={loading || crawlerRunning} className="gap-2">
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
            Refresh
          </Button>
          <nav className="flex items-center gap-1 bg-muted/50 p-1 rounded-md border border-border/20">
            {["catalog", "architecture", "behind_the_scenes"].map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-1.5 text-sm font-medium rounded-sm transition-all duration-200 capitalize ${
                  activeTab === tab
                    ? "bg-card text-foreground shadow-sm ring-1 ring-border/20"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted"
                }`}
              >
                {tab.replace(/_/g, " ")}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="p-6 md:p-8 max-w-7xl mx-auto">
        <AnimatePresence mode="wait">
          {activeTab === "catalog" && (
            <motion.div key="catalog" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }}>
              <CatalogTab state={state} loading={loading} running={crawlerRunning} onRunCrawler={handleRunCrawler} />
            </motion.div>
          )}
          {activeTab === "architecture" && (
            <motion.div key="architecture" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }}>
              <ArchitectureTab />
            </motion.div>
          )}
          {activeTab === "behind_the_scenes" && (
            <motion.div key="bts" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }}>
              <BehindTheScenesTab state={state} />
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}

function CatalogTab({
  state,
  loading,
  running,
  onRunCrawler,
}: {
  state: CrawlerState;
  loading: boolean;
  running: boolean;
  onRunCrawler: () => void;
}) {
  const [viewMode, setViewMode] = useState<"table" | "json">("table");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortBy, setSortBy] = useState("confidence");
  const [selectedRow, setSelectedRow] = useState<UiEntry | null>(null);

  const data = useMemo(() => state.catalog.map(toUiEntry), [state.catalog]);
  const counts = reportCounts(state.report);
  const processFailed =
    state.run?.completed_at && state.run.exit_code !== null && state.run.exit_code !== 0;
  const processStatus = state.run
    ? state.run.completed_at
      ? `crawler process exited ${state.run.exit_code ?? "unknown"} at ${formatDate(state.run.completed_at)}`
      : `crawler process started ${formatDate(state.run.started_at)}`
    : "crawler process has not been started from this UI session";

  const filteredData = useMemo(() => {
    let result = data;
    if (statusFilter !== "all") {
      result = result.filter((item) => item.status === statusFilter);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (item) =>
          item.title.toLowerCase().includes(q) ||
          item.id.toLowerCase().includes(q) ||
          item.sourceUrls.some((url) => url.toLowerCase().includes(q)),
      );
    }
    return [...result].sort((a, b) => {
      if (sortBy === "confidence") return b.confidence - a.confidence;
      if (sortBy === "paths") return b.paths - a.paths;
      if (sortBy === "fetched") return b.lastFetched.localeCompare(a.lastFetched);
      return 0;
    });
  }, [data, search, statusFilter, sortBy]);

  const rawVisibleEntries = filteredData.map((entry) => entry.raw);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          <StatCard value={state.stats.total} label="Total Specs" />
          <StatCard value={state.stats.active} label="Active" />
          <StatCard value={state.stats.stale} label="Stale" />
          <StatCard value={state.stats.invalid} label="Invalid" />
          <StatCard value={state.stats.rejected} label="Rejected" />
        </div>
        <div className="flex flex-col items-start gap-2 xl:items-end">
          <Button
            onClick={onRunCrawler}
            disabled={running}
            className="bg-primary hover:bg-primary/90 text-primary-foreground font-medium flex items-center gap-2"
          >
            <Play size={16} />
            {running ? "Crawler Running..." : "Run Crawler"}
          </Button>
          {running && (
            <p className="max-w-xs text-xs text-muted-foreground" aria-live="polite">
              This might take a while. The catalog, report, and logs will refresh as the crawler works.
            </p>
          )}
        </div>
      </div>

      <div className="border-b border-border/20 pb-4 text-xs font-mono text-muted-foreground">
        <div>
          Run {state.report?.run_id ?? "not recorded"} | {formatDate(state.report?.generated_at)} | discovered{" "}
          {counts.discovered ?? 0} sources | updated {counts.updated ?? 0} | unchanged {counts.unchanged ?? 0}
        </div>
        <div className={processFailed ? "mt-1 text-[#b91c1c]" : "mt-1"}>
          {processStatus}
        </div>
      </div>

      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative w-full sm:w-72">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search specs, ids, or sources..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="pl-8 bg-card border-border/50 text-sm"
            />
          </div>
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className="text-sm bg-card border border-border/50 rounded-md px-3 py-2 text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="all">All Status</option>
            <option value="active">Active</option>
            <option value="stale">Stale</option>
            <option value="invalid">Invalid</option>
          </select>
          <select
            value={sortBy}
            onChange={(event) => setSortBy(event.target.value)}
            className="text-sm bg-card border border-border/50 rounded-md px-3 py-2 text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="confidence">Sort by Validation</option>
            <option value="paths">Sort by Paths</option>
            <option value="fetched">Sort by Last Fetched</option>
          </select>
        </div>

        <div className="flex items-center bg-card border border-border/50 rounded-md p-1 self-start">
          <button
            onClick={() => setViewMode("table")}
            className={`px-3 py-1 text-xs font-medium rounded-sm ${viewMode === "table" ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground"}`}
          >
            Table
          </button>
          <button
            onClick={() => setViewMode("json")}
            className={`px-3 py-1 text-xs font-medium rounded-sm ${viewMode === "json" ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground"}`}
          >
            JSON
          </button>
        </div>
      </div>

      <Card className="border-border/40 shadow-sm overflow-hidden bg-card">
        {viewMode === "table" ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm border-collapse">
              <thead>
                <tr className="border-b border-border/40 bg-muted/20 text-muted-foreground font-medium">
                  <th className="px-4 py-3 font-medium">API Title</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">OAS</th>
                  <th className="px-4 py-3 font-medium">Version</th>
                  <th className="px-4 py-3 font-medium text-right">Paths</th>
                  <th className="px-4 py-3 font-medium">Sources</th>
                  <th className="px-4 py-3 font-medium">Validation Confidence</th>
                  <th className="px-4 py-3 font-medium">Last Checked</th>
                </tr>
              </thead>
              <tbody>
                {filteredData.map((row) => (
                  <tr
                    key={row.id}
                    onClick={() => setSelectedRow(row)}
                    className="border-b border-border/20 hover:bg-muted/30 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-4 font-medium text-foreground">
                      <div className="flex max-w-xs flex-col gap-1">
                        <span>{row.title}</span>
                        <span className="font-mono text-[10px] text-muted-foreground truncate">{row.id}</span>
                      </div>
                    </td>
                    <td className="px-4 py-4">
                      <StatusBadge status={row.status} />
                    </td>
                    <td className="px-4 py-4 text-muted-foreground font-mono text-xs">{row.oasVersion}</td>
                    <td className="px-4 py-4 text-muted-foreground font-mono text-xs">{row.latestVersion}</td>
                    <td className="px-4 py-4 text-right font-mono text-xs text-muted-foreground">{row.paths}</td>
                    <td className="px-4 py-4">
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-muted text-muted-foreground">
                        {row.sourceCount} source{row.sourceCount === 1 ? "" : "s"}
                      </span>
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-2 w-32">
                        <div className="h-1.5 flex-1 bg-muted rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${row.confidence > 80 ? "bg-[#10b981]" : row.confidence > 50 ? "bg-[#f59e0b]" : "bg-[#ef4444]"}`}
                            style={{ width: `${row.confidence}%` }}
                          />
                        </div>
                        <span className="text-xs font-mono text-muted-foreground w-7 text-right">{row.confidence}</span>
                      </div>
                    </td>
                    <td className="px-4 py-4 text-xs text-muted-foreground font-mono">{row.lastFetched}</td>
                  </tr>
                ))}
                {!loading && filteredData.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">
                      No specs found matching the current filters.
                    </td>
                  </tr>
                )}
                {loading && (
                  <tr>
                    <td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">
                      Loading crawler catalog...
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        ) : (
          <CodeBlock
            title="catalog.json"
            value={JSON.stringify(rawVisibleEntries, null, 2)}
            className="h-[520px]"
          />
        )}
      </Card>

      <LogPanel logs={state.logs} running={running} />

      <SpecModal selectedRow={selectedRow} onClose={() => setSelectedRow(null)} />
    </div>
  );
}

function SpecModal({ selectedRow, onClose }: { selectedRow: UiEntry | null; onClose: () => void }) {
  return (
    <AnimatePresence>
      {selectedRow && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex justify-end"
        >
          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 25, stiffness: 200 }}
            className="w-full max-w-3xl bg-card h-full shadow-2xl border-l border-border/40 overflow-y-auto flex flex-col"
          >
            <div className="flex items-center justify-between p-6 border-b border-border/20 sticky top-0 bg-card/95 backdrop-blur z-10">
              <div className="flex items-center gap-3">
                <h2 className="text-xl font-bold text-foreground">{selectedRow.title}</h2>
                <StatusBadge status={selectedRow.status} />
              </div>
              <button onClick={onClose} className="p-2 hover:bg-muted rounded-full text-muted-foreground transition-colors">
                <X size={20} />
              </button>
            </div>

            <div className="p-6 flex flex-col gap-8">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                <Meta label="OAS Version" value={selectedRow.oasVersion} />
                <Meta label="Latest Version" value={selectedRow.latestVersion} />
                <Meta label="Total Paths" value={selectedRow.paths.toString()} />
                <Meta label="Last Checked" value={selectedRow.lastFetched} />
              </div>

              <div>
                <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                  Validation Confidence <span className="text-[#10b981] font-mono">{selectedRow.confidence}/100</span>
                </h3>
                <div className="bg-muted/30 border border-border/20 rounded-md p-4">
                  <div className="flex flex-wrap gap-2">
                    {selectedRow.validationNotes.length ? (
                      selectedRow.validationNotes.map((note, index) => (
                        <span key={index} className="inline-flex items-center px-2 py-1 rounded bg-card border border-border/50 text-xs text-muted-foreground">
                          {note}
                        </span>
                      ))
                    ) : (
                      <span className="text-sm text-muted-foreground">No validation notes were recorded for this entry.</span>
                    )}
                  </div>
                </div>
              </div>

              <div>
                <h3 className="text-sm font-semibold mb-3">{selectedRow.sourceCount} source URL{selectedRow.sourceCount === 1 ? "" : "s"}</h3>
                <ul className="space-y-2">
                  {selectedRow.sourceUrls.map((url, index) => (
                    <li key={index} className="flex items-center gap-2 text-sm bg-muted/30 px-3 py-2 rounded border border-border/20">
                      <ExternalLink size={14} className="text-muted-foreground shrink-0" />
                      <span className="font-mono text-xs text-muted-foreground truncate">{url}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div>
                <h3 className="text-sm font-semibold mb-3">Latest Path Changes</h3>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  <PathList title="Removed" paths={selectedRow.diffRemoved} tone="red" />
                  <PathList title="Added" paths={selectedRow.diffAdded} tone="green" />
                </div>
              </div>

              <div>
                <h3 className="text-sm font-semibold mb-4">Version History</h3>
                {selectedRow.history.length ? (
                  <div className="space-y-4 pl-2 border-l-2 border-border/40 relative">
                    {selectedRow.history.map((entry, index) => (
                      <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} key={`${entry.version}-${index}`} className="relative pl-6">
                        <div className="absolute w-2 h-2 rounded-full bg-primary -left-[5px] top-1.5 ring-4 ring-card" />
                        <div className="bg-card border border-border/40 rounded-md p-3 shadow-sm">
                          <div className="flex items-center justify-between mb-2">
                            <span className="font-mono text-sm font-semibold">{entry.version}</span>
                            <span className="text-xs text-muted-foreground">{entry.date}</span>
                          </div>
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-mono text-muted-foreground">hash: {entry.hash}</span>
                            <span className={`font-mono font-medium ${entry.delta > 0 ? "text-[#10b981]" : entry.delta < 0 ? "text-[#ef4444]" : "text-[#f59e0b]"}`}>
                              {deltaLabel(entry.delta)}
                            </span>
                          </div>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No previous versions have been recorded yet.</p>
                )}
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function ArchitectureTab() {
  const [selectedNode, setSelectedNode] = useState<number | null>(1);

  const nodes = [
    {
      id: 1,
      title: "GitHub Search API",
      desc: "The crawler uses GitHub Code Search to locate OpenAPI and Swagger specs across public repositories. It fires filename queries and broader JSON queries so files named after an API, such as payments.json, can still be discovered.",
    },
    {
      id: 2,
      title: "Discovery Engine",
      desc: "Search results, direct seed URLs, and seed GitHub repositories are resolved into fetchable raw spec URLs. Discovery is separate from parsing so new sources can be added without rewriting the ingestion logic.",
    },
    {
      id: 3,
      title: "Fetch Queue",
      desc: "HTTP fetching uses retry and backoff. On re-crawls it sends ETag and Last-Modified validators, so a 304 response skips downloading and parsing entirely.",
    },
    {
      id: 4,
      title: "Parser + Validator",
      desc: "The parser handles Swagger 2.x and OpenAPI 3.x in YAML and JSON. It validates required fields before persisting anything, which keeps unrelated YAML or broken JSON out of the catalog.",
    },
    {
      id: 5,
      title: "Hash Engine",
      desc: "Each spec gets a raw content hash and a normalized semantic hash. That makes it possible to separate real API evolution from formatting-only edits.",
    },
    {
      id: 6,
      title: "Version Store",
      desc: "When a semantic change is detected, the previous version is preserved in immutable history with hashes, path count, timestamp, and added or removed paths.",
    },
    {
      id: 7,
      title: "Catalog JSON",
      desc: "The final output is long-lived JSON data with status, source URLs, confidence score, validation notes, hashes, and version history. The dashboard reads this file through the local API bridge.",
    },
  ];

  const activeNode = nodes.find((node) => node.id === selectedNode);

  return (
    <div className="flex flex-col gap-8 max-w-4xl mx-auto">
      <InfoBanner />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 relative">
        <div className="relative flex flex-col items-center py-4">
          <div className="absolute top-0 bottom-0 left-1/2 w-0.5 bg-border/30 -translate-x-1/2 z-0" />
          {nodes.map((node) => (
            <div key={node.id} className="relative z-10 w-full max-w-xs mb-8 last:mb-0">
              <button
                onClick={() => setSelectedNode(node.id)}
                className={`w-full text-center p-4 rounded-lg border shadow-sm transition-all duration-200 ${
                  selectedNode === node.id
                    ? "bg-primary text-primary-foreground border-primary shadow-md scale-105"
                    : "bg-card text-card-foreground border-border/40 hover:border-primary/50 hover:bg-muted/30"
                }`}
              >
                <span className="font-semibold text-sm">{node.title}</span>
              </button>
            </div>
          ))}
        </div>

        <motion.div key={activeNode?.id} initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="bg-card border border-border/40 rounded-lg p-6 shadow-md sticky top-32 self-start">
          <h3 className="text-lg font-bold mb-4 text-foreground">{activeNode?.title}</h3>
          <p className="text-sm text-muted-foreground leading-relaxed">{activeNode?.desc}</p>
        </motion.div>
      </div>
    </div>
  );
}

function BehindTheScenesTab({ state }: { state: CrawlerState }) {
  const counts = reportCounts(state.report);
  const steps = [
    { icon: Play, title: "Crawl starts", desc: "A run ID is assigned and structured JSON logging begins for the run." },
    { icon: Search, title: "GitHub Search API queried", desc: "Discovery queries cover explicit OpenAPI/Swagger filenames and broader JSON patterns." },
    { icon: GitBranch, title: "Seed repos and direct URLs fetched", desc: "Configured seed inputs provide deterministic bootstrapping independent of search results." },
    { icon: ShieldCheck, title: "Validation before persistence", desc: "Broken JSON, unrelated YAML, missing title, missing version, and invalid paths are rejected." },
    { icon: FileCode, title: "Parsing and metadata extraction", desc: "The parser extracts title, version, description, servers, paths, tags, and normalized path keys." },
    { icon: BarChart2, title: "Validation confidence computed", desc: "Confidence score and notes explain why a spec was trusted." },
    { icon: Hash, title: "Content and semantic hashes computed", desc: "Raw file changes and meaningful API changes are tracked separately." },
    { icon: Database, title: "Duplicate detection", desc: "Identical semantic specs are collapsed into one catalog entry with all source URLs preserved." },
    { icon: GitCompare, title: "Version comparison", desc: "The crawler determines whether each spec is changed, unchanged, format-only, stale, or invalid." },
    { icon: Diff, title: "Changelog diff generated", desc: "Added and removed paths are stored explicitly when a real update is detected." },
    { icon: Archive, title: "Immutable history written", desc: "Previous versions remain available in the catalog history." },
    { icon: RefreshCw, title: "Conditional fetch on re-crawls", desc: "ETag and Last-Modified validators skip unchanged specs." },
    { icon: Activity, title: "Lifecycle states updated", desc: "Specs move between active, stale, and invalid without silently disappearing." },
    { icon: FileText, title: "Run report written", desc: "The run report summarizes the operational result of the crawl." },
  ];

  const summary = [
    { label: "New", value: counts.new ?? 0 },
    { label: "Updated", value: counts.updated ?? 0 },
    { label: "Unchanged", value: counts.unchanged ?? 0 },
    { label: "Stale", value: counts.stale ?? 0 },
    { label: "Rejected", value: counts.rejected ?? 0 },
    { label: "Duplicates", value: counts.duplicates_collapsed ?? 0 },
    { label: "Format-only", value: counts.format_only_changes ?? 0 },
    { label: "Failed", value: counts.failed ?? 0 },
  ];

  return (
    <div className="flex flex-col gap-10">
      <InfoBanner />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
        <div>
          <h3 className="text-lg font-bold mb-6 border-b border-border/20 pb-2">Execution Flow</h3>
          <div className="space-y-6">
            {steps.map((step, index) => {
              const Icon = step.icon;
              return (
                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.04 }} key={step.title} className="flex gap-4 group">
                  <div className="flex flex-col items-center">
                    <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center border border-border/40 group-hover:bg-primary group-hover:text-primary-foreground group-hover:border-primary transition-colors shrink-0">
                      <Icon size={14} />
                    </div>
                    {index < steps.length - 1 && <div className="w-px h-full bg-border/40 my-1 group-hover:bg-primary/30 transition-colors" />}
                  </div>
                  <div className="pb-6">
                    <h4 className="text-sm font-bold text-foreground mb-1">{step.title}</h4>
                    <p className="text-sm text-muted-foreground leading-relaxed">{step.desc}</p>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>

        <div className="flex flex-col gap-6">
          <div>
            <h3 className="text-lg font-bold mb-6 border-b border-border/20 pb-2">Latest Run Report</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
              {summary.map((stat) => (
                <div key={stat.label} className="bg-card border border-border/40 rounded p-3 text-center">
                  <div className="text-2xl font-bold text-foreground mb-1">{stat.value}</div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{stat.label}</div>
                </div>
              ))}
            </div>

            <div className="flex flex-col gap-4">
              <CodeBlock title="structured_logs.jsonl" value={state.logs.slice(-10).map((log) => JSON.stringify(log)).join("\n")} className="h-[360px]" />
              <CodeBlock title="run_report.json" value={JSON.stringify(state.report, null, 2)} className="h-[360px]" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function LogPanel({ logs, running }: { logs: any[]; running: boolean }) {
  const visibleLogs = logs.slice(-40);
  return (
    <div className="mt-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-foreground">Crawler Logs</h3>
        <span className="flex items-center gap-1.5 text-xs text-[#10b981] font-mono bg-[#10b981]/10 px-2 py-0.5 rounded">
          <div className="w-1.5 h-1.5 rounded-full bg-[#10b981] animate-pulse" />
          {running ? "Running..." : "Tailing latest file logs"}
        </span>
      </div>
      <div className="bg-[#1E1E2E] rounded-md border border-border/20 h-64 overflow-hidden p-4 font-mono text-[11px] leading-relaxed flex flex-col justify-end">
        <div className="flex flex-col gap-1 justify-end h-full overflow-y-auto">
          {visibleLogs.length ? (
            visibleLogs.map((log, index) => (
              <div key={index} className="flex gap-3 text-[#A6ACCD] break-all">
                <span className="text-[#5A5A72] shrink-0">{logTimestamp(log).split("T")[1]?.replace("Z", "") ?? ""}</span>
                <span className={`shrink-0 ${String(log.level).toLowerCase() === "warning" || String(log.level).toLowerCase() === "warn" ? "text-[#f59e0b]" : "text-[#3b82f6]"}`}>
                  [{String(log.level ?? "info").toLowerCase()}]
                </span>
                <span className="text-[#e2e8f0]">{logMessage(log)}</span>
              </div>
            ))
          ) : (
            <span className="text-[#A6ACCD]">No crawler logs found yet. Run the crawler to generate logs.</span>
          )}
        </div>
      </div>
    </div>
  );
}

function CodeBlock({ title, value, className = "" }: { title: string; value: string; className?: string }) {
  const copy = () => navigator.clipboard?.writeText(value);
  return (
    <div className={`bg-[#1E1E2E] rounded-md border border-border/20 overflow-hidden flex flex-col ${className}`}>
      <div className="bg-[#16161D] px-4 py-2 border-b border-border/10 flex justify-between items-center">
        <span className="text-xs font-mono text-muted-foreground">{title}</span>
        <button onClick={copy} className="text-muted-foreground hover:text-foreground">
          <Copy size={14} />
        </button>
      </div>
      <pre className="p-4 font-mono text-[11px] text-[#A6ACCD] overflow-auto whitespace-pre-wrap">
        {value || "No data recorded yet."}
      </pre>
    </div>
  );
}

function InfoBanner() {
  return (
    <div className="bg-[#e0e7ff]/30 border border-[#6366f1]/20 rounded-md p-4 flex items-start gap-3">
      <Info className="text-[#6366f1] shrink-0 mt-0.5" size={18} />
      <p className="text-sm text-foreground/80 leading-relaxed">
        Reliable specs are the input layer for SDKs, docs, portals, and AI tools. This dashboard reads the real crawler
        artifacts and makes that input layer inspectable.
      </p>
    </div>
  );
}

function PathList({ title, paths, tone }: { title: string; paths: string[]; tone: "red" | "green" }) {
  const color = tone === "red" ? "#ef4444" : "#10b981";
  const sign = tone === "red" ? "-" : "+";
  return (
    <div className={`border rounded-md overflow-hidden`} style={{ borderColor: `${color}33`, backgroundColor: `${color}0d` }}>
      <div className="px-3 py-2 text-xs font-semibold border-b" style={{ color, borderColor: `${color}33`, backgroundColor: `${color}1a` }}>
        {title} ({paths.length})
      </div>
      <ul className="p-2 space-y-1">
        {paths.length ? (
          paths.map((pathValue, index) => (
            <li key={index} className="font-mono text-[10px] break-all" style={{ color }}>
              {sign} {pathValue}
            </li>
          ))
        ) : (
          <li className="text-xs text-muted-foreground italic p-2">None recorded</li>
        )}
      </ul>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground mb-1">{label}</div>
      <div className="font-mono text-sm break-all">{value}</div>
    </div>
  );
}

function StatCard({ value, label }: { value: number | string; label: string }) {
  return (
    <div className="flex flex-col rounded-md border border-border/40 bg-card px-4 py-3 shadow-sm">
      <div className="text-2xl font-bold text-foreground leading-none mb-1">{value}</div>
      <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</div>
    </div>
  );
}

function StatusBadge({ status }: { status: Status }) {
  if (status === "active") {
    return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-[#10b981]/10 text-[#047857] border border-[#10b981]/20">Active</span>;
  }
  if (status === "stale") {
    return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-[#f59e0b]/10 text-[#b45309] border border-[#f59e0b]/20">Stale</span>;
  }
  if (status === "invalid") {
    return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-[#ef4444]/10 text-[#b91c1c] border border-[#ef4444]/20">Invalid</span>;
  }
  return <Badge variant="outline">{status}</Badge>;
}
