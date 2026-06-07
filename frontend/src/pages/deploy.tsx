import * as React from "react"
import { Link, useNavigate } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Copy,
  FileArchive,
  FolderGit2,
  GitBranch,
  Pencil,
  Plus,
  Rocket,
  Trash2,
  UploadCloud,
  Webhook,
  Workflow,
} from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useConfirm } from "@/components/confirm-dialog"
import {
  api,
  getJSON,
  type DeployNodeResult,
  type DeployRecord,
  type DeployRepo,
  type NodeInfo,
} from "@/lib/api"
import { useNode } from "@/lib/node-context"
import { cn } from "@/lib/utils"

interface FolderEntry {
  folder: string
  project: string
  modified: string
}

interface FoldersResponse {
  status: string
  projects_dir: string
  latest_folder: string
  folders: FolderEntry[]
}

function nowVersion() {
  // mirror legacy get_now_string(): 2026-06-06T22_30_36
  return new Date().toISOString().slice(0, 19).replace(/:/g, "_")
}

function toastNodeResults(results: DeployNodeResult[] | undefined) {
  for (const r of results ?? []) {
    if (r.status !== "ok")
      toast.error(`node ${r.node} (${r.server}): ${r.message || `status ${r.status_code}`}`)
  }
}

export default function DeployPage() {
  const { node } = useNode()
  const navigate = useNavigate()
  const [file, setFile] = React.useState<File | null>(null)
  const [folder, setFolder] = React.useState("")
  const [project, setProject] = React.useState("")
  const [version, setVersion] = React.useState(nowVersion)
  const [dragOver, setDragOver] = React.useState(false)
  const [nodes, setNodes] = React.useState<number[]>([node])

  // keep the default selection in sync when the topbar node changes
  React.useEffect(() => setNodes([node]), [node])

  const { data: scan, isLoading } = useQuery({
    queryKey: ["deploy-folders", node],
    queryFn: () => getJSON<FoldersResponse>(`/api/${node}/deploy/folders/`),
  })

  const qc = useQueryClient()
  const deploy = useMutation({
    mutationFn: async (src: { kind: "file"; file: File } | { kind: "folder"; folder: string }) => {
      const fd = new FormData()
      fd.set("as_json", "True")
      fd.set("project", project)
      fd.set("version", version)
      fd.set("nodes", nodes.join(","))
      if (src.kind === "file") fd.set("file", src.file)
      else fd.set("folder", src.folder)
      const res = await fetch(`/${node}/deploy/upload/`, { method: "POST", body: fd })
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      return res.json() as Promise<Record<string, unknown>>
    },
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["deploy-history"] })
      if (res.status === "ok") {
        toastNodeResults(res.results as DeployNodeResult[] | undefined)
        toast.success(
          `Deployed ${res.project} (${res.version})${res.overall === "partial" ? " — some nodes failed" : ""}`,
        )
        navigate(`/schedule?project=${encodeURIComponent(String(res.project))}`)
      } else {
        toastNodeResults(res.results as DeployNodeResult[] | undefined)
        toast.error(`${res.alert ?? "Deploy failed"}: ${res.text ?? res.message ?? ""}`)
      }
    },
    onError: (e) => toast.error(`Deploy failed: ${e.message}`),
  })

  const pickFolder = (f: FolderEntry) => {
    setFolder(f.folder)
    setProject((p) => p || f.project)
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Deploy Project</h2>
        <span className="font-mono text-xs text-muted-foreground">node {node}</span>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Target</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="grid gap-2">
            <Label htmlFor="dp-project">Project name</Label>
            <Input
              id="dp-project"
              placeholder="auto from scrapy.cfg / folder"
              value={project}
              onChange={(e) => setProject(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="dp-version">Version</Label>
            <Input
              id="dp-version"
              className="font-mono"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
            />
          </div>
          <div className="grid gap-2 sm:col-span-2">
            <Label>Deploy to nodes</Label>
            <NodeMultiSelect value={nodes} onChange={setNodes} />
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="folder">
        <TabsList>
          <TabsTrigger value="folder">
            <FolderGit2 className="size-4" /> Server folder
          </TabsTrigger>
          <TabsTrigger value="upload">
            <UploadCloud className="size-4" /> Upload egg / archive
          </TabsTrigger>
          <TabsTrigger value="git">
            <GitBranch className="size-4" /> From git
          </TabsTrigger>
          <TabsTrigger value="auto">
            <Webhook className="size-4" /> Auto-deploy
          </TabsTrigger>
          <TabsTrigger value="ci">
            <Workflow className="size-4" /> CI / GitHub
          </TabsTrigger>
        </TabsList>

        <TabsContent value="folder">
          <Card>
            <CardHeader>
              <CardTitle className="font-mono text-xs text-muted-foreground">
                {scan?.projects_dir ?? "…"}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {isLoading && <Skeleton className="h-24 rounded-lg" />}
              {scan && scan.folders.length === 0 && (
                <p className="py-4 text-center text-sm text-muted-foreground">
                  No scrapy projects found (folders containing scrapy.cfg).
                </p>
              )}
              {scan?.folders.map((f) => (
                <button
                  key={f.folder}
                  type="button"
                  onClick={() => pickFolder(f)}
                  className={cn(
                    "flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border px-3 py-2.5 text-left transition-colors",
                    folder === f.folder
                      ? "border-primary/50 bg-accent/40"
                      : "border-border bg-secondary/30 hover:border-primary/30",
                  )}
                >
                  <FolderGit2 className="size-4 text-muted-foreground" />
                  <span className="font-medium">{f.folder}</span>
                  <span className="font-mono text-xs text-muted-foreground">→ {f.project}</span>
                  {f.folder === scan.latest_folder && (
                    <Badge variant="secondary" className="text-[10px]">
                      latest
                    </Badge>
                  )}
                  <span className="ml-auto font-mono text-[11px] text-muted-foreground">
                    {f.modified}
                  </span>
                </button>
              ))}
              <Button
                className="mt-2 self-start"
                disabled={!folder || nodes.length === 0 || deploy.isPending}
                onClick={() => deploy.mutate({ kind: "folder", folder })}
              >
                <Rocket className="size-4" />
                {deploy.isPending ? "Building egg…" : `Deploy ${folder || "folder"}`}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="upload">
          <Card>
            <CardContent className="flex flex-col gap-3">
              <label
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragOver(true)
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault()
                  setDragOver(false)
                  const f = e.dataTransfer.files[0]
                  if (f) setFile(f)
                }}
                className={cn(
                  "flex cursor-pointer flex-col items-center gap-2 rounded-lg border border-dashed px-6 py-10 text-center transition-colors",
                  dragOver ? "border-primary bg-accent/30" : "border-border bg-secondary/20",
                )}
              >
                <FileArchive className="size-6 text-muted-foreground" />
                {file ? (
                  <span className="font-mono text-sm">{file.name}</span>
                ) : (
                  <>
                    <span className="text-sm">Drop an egg / zip / tar.gz here, or click to browse</span>
                    <span className="font-mono text-[11px] text-muted-foreground">
                      archives are unpacked and built into an egg server-side
                    </span>
                  </>
                )}
                <input
                  type="file"
                  accept=".egg,.zip,.tar.gz,.gz"
                  className="hidden"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
              </label>
              <Button
                className="self-start"
                disabled={!file || nodes.length === 0 || deploy.isPending}
                onClick={() => file && deploy.mutate({ kind: "file", file })}
              >
                <Rocket className="size-4" />
                {deploy.isPending ? "Deploying…" : "Deploy file"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="git">
          <GitDeployCard node={node} nodes={nodes} />
        </TabsContent>

        <TabsContent value="auto">
          <AutoDeployCard />
        </TabsContent>

        <TabsContent value="ci">
          <CiTemplateCard />
        </TabsContent>
      </Tabs>

      <RecentDeploysCard />
    </div>
  )
}

function NodeMultiSelect({
  value,
  onChange,
}: {
  value: number[]
  onChange: (nodes: number[]) => void
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["nodes"],
    queryFn: api.nodes,
    staleTime: 60_000,
  })
  if (isLoading) return <Skeleton className="h-8 w-64 rounded-lg" />
  const all: NodeInfo[] = data?.nodes ?? []
  const toggle = (n: number) =>
    onChange(value.includes(n) ? value.filter((x) => x !== n) : [...value, n].sort((a, b) => a - b))
  return (
    <div className="flex flex-wrap gap-1.5">
      {all.map((n) => {
        const active = value.includes(n.node)
        return (
          <button
            key={n.node}
            type="button"
            onClick={() => toggle(n.node)}
            className={cn(
              "rounded-full border px-3 py-1 font-mono text-xs transition-colors",
              active
                ? "border-primary/60 bg-primary/15 text-primary"
                : "border-border bg-secondary/40 text-muted-foreground hover:border-primary/30",
            )}
          >
            {n.node} · {n.server}
          </button>
        )
      })}
      {value.length === 0 && (
        <span className="self-center text-xs text-destructive">select at least one node</span>
      )}
    </div>
  )
}

function GitDeployCard({ node, nodes }: { node: number; nodes: number[] }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [repo, setRepo] = React.useState("")
  const [ref, setRef] = React.useState("main")
  const [token, setToken] = React.useState("")
  const [project, setProject] = React.useState("")
  const [version, setVersion] = React.useState("")
  const [error, setError] = React.useState("")
  const [busy, setBusy] = React.useState(false)

  const submit = async () => {
    setError("")
    setBusy(true)
    try {
      const res = await api.deployGit({ repo, ref, token, project, version, node, nodes })
      qc.invalidateQueries({ queryKey: ["deploy-history"] })
      if (res.status === "ok") {
        toastNodeResults(res.results as DeployNodeResult[] | undefined)
        toast.success(`Deployed ${res.project} (${res.version}) from git`)
        navigate(`/schedule?project=${encodeURIComponent(String(res.project))}`)
      } else {
        toastNodeResults(res.results as DeployNodeResult[] | undefined)
        setError(String(res.message ?? res.text ?? res.alert ?? "Deploy failed"))
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-2 sm:col-span-2">
          <Label htmlFor="git-repo">Repository (https)</Label>
          <Input
            id="git-repo"
            placeholder="https://github.com/you/your-scrapy-project"
            value={repo}
            onChange={(e) => setRepo(e.target.value)}
            className="font-mono text-xs"
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="git-ref">Branch / tag</Label>
          <Input id="git-ref" value={ref} onChange={(e) => setRef(e.target.value)}
                 className="font-mono text-xs" />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="git-token">Access token (private repos)</Label>
          <Input
            id="git-token"
            type="password"
            autoComplete="off"
            placeholder="optional"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            className="font-mono text-xs"
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="git-project">Project name</Label>
          <Input id="git-project" value={project} onChange={(e) => setProject(e.target.value)} />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="git-version">Version</Label>
          <Input
            id="git-version"
            placeholder="auto: short commit sha"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
            className="font-mono text-xs"
          />
        </div>
        {error && (
          <p className="font-mono text-xs text-destructive sm:col-span-2">{error}</p>
        )}
        <Button
          className="self-start"
          disabled={busy || !repo || !project || nodes.length === 0}
          onClick={submit}
        >
          <Rocket className="size-4" /> {busy ? "Cloning & building…" : "Deploy from git"}
        </Button>
      </CardContent>
    </Card>
  )
}

// ------------------------------------------------------------------ auto-deploy (webhooks)
const EMPTY_REPO = { name: "", repo_url: "", ref: "main", project: "", access_token: "", nodes: [1] }

function AutoDeployCard() {
  const qc = useQueryClient()
  const { confirm: confirmDialog, dialog: confirmUI } = useConfirm()
  const { data, isLoading } = useQuery({ queryKey: ["deploy-repos"], queryFn: api.deployRepos })
  const [editing, setEditing] = React.useState<DeployRepo | "new" | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ["deploy-repos"] })

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      api.updateDeployRepo(id, { enabled }),
    onSuccess: invalidate,
    onError: (e) => toast.error(`Update failed: ${e.message}`),
  })

  const del = useMutation({
    mutationFn: (id: number) => api.deleteDeployRepo(id),
    onSuccess: (res) => {
      if (res.status === "ok") toast.success("Repo removed")
      else toast.error(res.message ?? "Delete failed")
      invalidate()
    },
    onError: (e) => toast.error(`Delete failed: ${e.message}`),
  })

  const copy = (text: string, what: string) => {
    navigator.clipboard.writeText(text)
    toast.success(`${what} copied`)
  }

  const repos = data?.repos ?? []
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="text-sm font-semibold">Auto-deploy from GitHub</CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">
            Register a repo, add its webhook to GitHub — every push to the branch deploys
            automatically (version = short commit sha).
          </p>
        </div>
        <Button size="sm" className="h-8 gap-1.5 text-xs" onClick={() => setEditing("new")}>
          <Plus className="size-3.5" /> Add repo
        </Button>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {isLoading && <Skeleton className="h-20 rounded-lg" />}
        {!isLoading && repos.length === 0 && (
          <p className="py-4 text-center text-sm text-muted-foreground">
            No repos registered yet.
          </p>
        )}
        {repos.map((r) => (
          <div key={r.id} className="rounded-lg border border-border bg-secondary/30 px-3 py-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <Webhook className="size-4 text-muted-foreground" />
              <span className="font-medium">{r.name}</span>
              <span className="font-mono text-xs text-muted-foreground">
                {r.repo_url.replace(/^https:\/\//, "")} @ {r.ref} → {r.project}
              </span>
              <Badge variant="outline" className="font-mono text-[10px]">
                nodes {r.nodes.join(",")}
              </Badge>
              {r.has_token && (
                <Badge variant="secondary" className="text-[10px]">
                  private
                </Badge>
              )}
              <div className="ml-auto flex items-center gap-1.5">
                <Switch
                  checked={r.enabled}
                  onCheckedChange={(enabled) => toggle.mutate({ id: r.id, enabled })}
                  aria-label={`Enable ${r.name}`}
                />
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-7"
                  aria-label={`Edit ${r.name}`}
                  onClick={() => setEditing(r)}
                >
                  <Pencil className="size-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-7 text-destructive hover:text-destructive"
                  aria-label={`Delete ${r.name}`}
                  onClick={async () =>
                    (await confirmDialog({
                      title: `Remove repo "${r.name}"?`,
                      description: "Its webhook deliveries will return 404. Deploy history is kept.",
                      confirmLabel: "Remove repo",
                      destructive: true,
                    })) && del.mutate(r.id)
                  }
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-border pt-2">
              <span className="font-mono text-[11px] text-muted-foreground">
                {window.location.origin}
                {r.webhook_path}
              </span>
              <Button
                variant="outline"
                size="sm"
                className="h-6 gap-1 text-[11px]"
                onClick={() => copy(window.location.origin + r.webhook_path, "Webhook URL")}
              >
                <Copy className="size-3" /> URL
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-6 gap-1 text-[11px]"
                onClick={() => copy(r.webhook_secret, "Webhook secret")}
              >
                <Copy className="size-3" /> Secret
              </Button>
              <span className="text-[11px] text-muted-foreground">
                GitHub → repo Settings → Webhooks → content type{" "}
                <span className="font-mono">application/json</span>, events: push
              </span>
            </div>
          </div>
        ))}
      </CardContent>
      {editing && (
        <RepoDialog
          repo={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={invalidate}
        />
      )}
      {confirmUI}
    </Card>
  )
}

function RepoDialog({
  repo,
  onClose,
  onSaved,
}: {
  repo: DeployRepo | null
  onClose: () => void
  onSaved: () => void
}) {
  const [form, setForm] = React.useState(() =>
    repo
      ? { name: repo.name, repo_url: repo.repo_url, ref: repo.ref, project: repo.project,
          access_token: "", nodes: repo.nodes }
      : EMPTY_REPO,
  )
  const [error, setError] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }))

  const save = async () => {
    setError("")
    setBusy(true)
    try {
      const body: Record<string, unknown> = {
        name: form.name, repo_url: form.repo_url, ref: form.ref,
        project: form.project, nodes: form.nodes,
      }
      // only send the token when the user typed one (edits keep the stored token)
      if (form.access_token) body.access_token = form.access_token
      const res = repo
        ? await api.updateDeployRepo(repo.id, body)
        : await api.createDeployRepo(body)
      if (res.status === "ok") {
        toast.success(repo ? "Repo updated" : `Repo added — copy the webhook URL + secret into GitHub`)
        onSaved()
        onClose()
      } else {
        setError(res.message ?? "Save failed")
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{repo ? `Edit ${repo.name}` : "Register a repo"}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="grid gap-2">
            <Label htmlFor="rd-name">Name</Label>
            <Input id="rd-name" value={form.name} onChange={(e) => set("name", e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="rd-project">Project</Label>
            <Input id="rd-project" value={form.project}
                   onChange={(e) => set("project", e.target.value)} />
          </div>
          <div className="grid gap-2 sm:col-span-2">
            <Label htmlFor="rd-url">Repository (https)</Label>
            <Input id="rd-url" className="font-mono text-xs"
                   placeholder="https://github.com/you/your-scrapy-project"
                   value={form.repo_url} onChange={(e) => set("repo_url", e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="rd-ref">Branch</Label>
            <Input id="rd-ref" className="font-mono text-xs" value={form.ref}
                   onChange={(e) => set("ref", e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="rd-token">Access token</Label>
            <Input id="rd-token" type="password" autoComplete="off"
                   placeholder={repo?.has_token ? "(unchanged)" : "optional, private repos"}
                   value={form.access_token}
                   onChange={(e) => set("access_token", e.target.value)} />
          </div>
          <div className="grid gap-2 sm:col-span-2">
            <Label>Deploy to nodes</Label>
            <NodeMultiSelect value={form.nodes} onChange={(nodes) => set("nodes", nodes)} />
          </div>
          {error && <p className="font-mono text-xs text-destructive sm:col-span-2">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={busy || !form.name || !form.repo_url || !form.project || form.nodes.length === 0}
            onClick={save}
          >
            {busy ? "Saving…" : repo ? "Save changes" : "Register repo"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ------------------------------------------------------------------ history
const SOURCE_LABEL: Record<DeployRecord["source"], string> = {
  file: "upload",
  folder: "folder",
  git: "git",
  push: "ci push",
  webhook: "webhook",
}

function RecentDeploysCard() {
  const { data, isLoading } = useQuery({
    queryKey: ["deploy-history"],
    queryFn: () => api.deployHistory({ perPage: 15 }),
    refetchInterval: 15_000,
  })

  const records = data?.records ?? []
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-semibold">Recent deploys</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-1.5">
        {isLoading && <Skeleton className="h-24 rounded-lg" />}
        {!isLoading && records.length === 0 && (
          <p className="py-4 text-center text-sm text-muted-foreground">No deploys recorded yet.</p>
        )}
        {records.map((r) => (
          <div
            key={r.id}
            className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-border bg-secondary/20 px-3 py-2"
          >
            <span className="font-mono text-[11px] text-muted-foreground">{r.created_at}</span>
            <Badge variant="outline" className="font-mono text-[10px] uppercase">
              {SOURCE_LABEL[r.source] ?? r.source}
            </Badge>
            <span className="font-mono text-xs">
              {r.project}
              {r.version && (
                <>
                  {" @ "}
                  <Link
                    to={`/code/${encodeURIComponent(r.project)}/${encodeURIComponent(r.version)}`}
                    className="text-primary hover:underline"
                    title="View code"
                  >
                    {r.version}
                  </Link>
                </>
              )}
            </span>
            {r.actor && (
              <span className="font-mono text-[11px] text-muted-foreground">by {r.actor}</span>
            )}
            <div className="ml-auto flex items-center gap-1">
              {r.results.length > 0 ? (
                r.results.map((n) => (
                  <span
                    key={n.node}
                    title={`node ${n.node} (${n.server}): ${n.status}${n.message ? ` — ${n.message}` : ""}`}
                    className={cn(
                      "rounded-full px-2 py-0.5 font-mono text-[10px]",
                      n.status === "ok"
                        ? "bg-primary/15 text-primary"
                        : "bg-destructive/15 text-destructive",
                    )}
                  >
                    n{n.node}
                  </span>
                ))
              ) : (
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 font-mono text-[10px]",
                    r.status === "ok"
                      ? "bg-primary/15 text-primary"
                      : r.status === "pending"
                        ? "bg-secondary text-muted-foreground"
                        : "bg-destructive/15 text-destructive",
                  )}
                  title={r.message ?? undefined}
                >
                  {r.status}
                </span>
              )}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function CiTemplateCard() {
  const [origin] = React.useState(() => window.location.origin)
  const yaml = `name: deploy-spiders

on:
  push:
    tags: ["v*"]          # deploy on version tags; or use branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - name: Build egg
        run: |
          pip install scrapyd-client
          scrapyd-deploy --build-egg=project.egg
      - name: Push to ScrapydWeb
        run: |
          curl --fail -X POST "${origin}/api/deploy/push" \\
            -H "X-Deploy-Token: \${{ secrets.SCRAPYDWEB_DEPLOY_TOKEN }}" \\
            -F "egg=@project.egg" \\
            -F "project=YOUR_PROJECT" \\
            -F "nodes=1" \\
            -F "version=\${{ github.ref_name }}"`

  return (
    <Card>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">
          Prefer the <span className="font-mono text-xs">Auto-deploy</span> tab if this instance is
          reachable from GitHub — no CI config needed. Use this push-token workflow when you want
          the egg built in CI. 1. Set a{" "}
          <span className="font-mono text-xs">CI deploy token</span> in Settings → CI / Deploy.
          &nbsp;2. Add it to your repo as the{" "}
          <span className="font-mono text-xs">SCRAPYDWEB_DEPLOY_TOKEN</span> secret. &nbsp;3.
          Commit this workflow as{" "}
          <span className="font-mono text-xs">.github/workflows/deploy.yml</span>:
        </p>
        <div className="relative">
          <Button
            variant="outline"
            size="sm"
            className="absolute right-2 top-2 h-7 gap-1 text-xs"
            onClick={() => {
              navigator.clipboard.writeText(yaml)
              toast.success("Workflow copied")
            }}
          >
            <Copy className="size-3" /> Copy
          </Button>
          <pre className="overflow-auto rounded-lg border border-border bg-background/60 p-4 font-mono text-xs leading-relaxed">
            {yaml}
          </pre>
        </div>
        <p className="text-xs text-muted-foreground">
          The instance must be reachable from GitHub runners ({origin}).{" "}
          <span className="font-mono">nodes</span> takes a comma-separated node list. Version lands
          as the git tag — code is browsable per version on the Projects page.
        </p>
      </CardContent>
    </Card>
  )
}
