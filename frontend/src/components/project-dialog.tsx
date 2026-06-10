import * as React from "react"
import { Copy, RefreshCw } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { NodeMultiSelect } from "@/components/node-multi-select"
import { api, type DeploySource, type Project } from "@/lib/api"

const SOURCES: { value: DeploySource; label: string; hint: string }[] = [
  { value: "manual", label: "Manual", hint: "deploy by hand (upload / folder / git) — no saved config" },
  { value: "folder", label: "Server folder", hint: "build from a folder in the projects dir" },
  { value: "git", label: "From git", hint: "clone + build a repo on demand (one-click Deploy)" },
  { value: "webhook", label: "GitHub webhook", hint: "auto-deploy on every push to the branch" },
]

function copy(text: string, what: string) {
  navigator.clipboard.writeText(text)
  toast.success(`${what} copied`)
}

export function ProjectDialog({
  project,
  defaultName,
  onClose,
  onSaved,
}: {
  project: Project | null
  defaultName?: string
  onClose: () => void
  onSaved: (p: Project) => void
}) {
  const [form, setForm] = React.useState(() => ({
    name: project?.name ?? defaultName ?? "",
    description: project?.description ?? "",
    deploy_source: (project?.deploy_source ?? "manual") as DeploySource,
    repo_url: project?.repo_url ?? "",
    ref: project?.ref ?? "main",
    access_token: "",
    nodes: project?.default_nodes ?? [1],
  }))
  const [secret, setSecret] = React.useState(project?.webhook_secret ?? null)
  const [webhookPath, setWebhookPath] = React.useState(project?.webhook_path ?? null)
  const [error, setError] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }))

  const needsRepo = form.deploy_source === "git" || form.deploy_source === "webhook"

  const save = async (rotate = false) => {
    setError("")
    setBusy(true)
    try {
      const body: Record<string, unknown> = {
        name: form.name,
        description: form.description,
        deploy_source: form.deploy_source,
        nodes: form.nodes,
        ref: form.ref,
        repo_url: needsRepo ? form.repo_url : "",
      }
      if (form.access_token) body.access_token = form.access_token
      if (rotate) body.rotate_secret = true
      const res = project
        ? await api.updateProject(project.id, body)
        : await api.createProject(body)
      if (res.status === "ok" && res.project) {
        setSecret(res.project.webhook_secret)
        setWebhookPath(res.project.webhook_path)
        toast.success(project ? "Project saved" : `Project "${res.project.name}" created`)
        onSaved(res.project)
        if (!rotate) onClose()
      } else {
        setError(res.message ?? "Save failed")
      }
    } finally {
      setBusy(false)
    }
  }

  const valid = form.name && form.nodes.length > 0 && (!needsRepo || form.repo_url)

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{project ? `Edit ${project.name}` : "Create a project"}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="grid gap-2">
            <Label htmlFor="pd-name">Name</Label>
            <Input
              id="pd-name"
              className="font-mono"
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              disabled={!!project}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="pd-source">Deploy mechanism</Label>
            <Select value={form.deploy_source} onValueChange={(v) => set("deploy_source", v)}>
              <SelectTrigger id="pd-source" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SOURCES.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <p className="-mt-2 text-[11px] text-muted-foreground sm:col-span-2">
            {SOURCES.find((s) => s.value === form.deploy_source)?.hint}
          </p>

          <div className="grid gap-2 sm:col-span-2">
            <Label htmlFor="pd-desc">Description (optional)</Label>
            <Textarea
              id="pd-desc"
              className="min-h-16"
              value={form.description}
              onChange={(e) => set("description", e.target.value)}
            />
          </div>

          {needsRepo && (
            <>
              <div className="grid gap-2 sm:col-span-2">
                <Label htmlFor="pd-url">Repository (https)</Label>
                <Input
                  id="pd-url"
                  className="font-mono text-xs"
                  placeholder="https://github.com/you/your-scrapy-project"
                  value={form.repo_url}
                  onChange={(e) => set("repo_url", e.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="pd-ref">Branch / tag</Label>
                <Input
                  id="pd-ref"
                  className="font-mono text-xs"
                  value={form.ref}
                  onChange={(e) => set("ref", e.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="pd-token">Access token</Label>
                <Input
                  id="pd-token"
                  type="password"
                  autoComplete="off"
                  placeholder={project?.has_token ? "(unchanged)" : "optional, private repos"}
                  value={form.access_token}
                  onChange={(e) => set("access_token", e.target.value)}
                />
              </div>
            </>
          )}

          <div className="grid gap-2 sm:col-span-2">
            <Label>Default deploy nodes</Label>
            <NodeMultiSelect value={form.nodes} onChange={(nodes) => set("nodes", nodes)} />
          </div>

          {form.deploy_source === "webhook" && webhookPath && secret && (
            <div className="grid gap-2 rounded-lg border border-border bg-secondary/30 p-3 sm:col-span-2">
              <p className="text-[11px] font-medium text-muted-foreground">
                GitHub → repo Settings → Webhooks → content type{" "}
                <span className="font-mono">application/json</span>, events: push
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <span className="truncate font-mono text-[11px]">
                  {window.location.origin}
                  {webhookPath}
                </span>
                <Button variant="outline" size="sm" className="h-6 gap-1 text-[11px]"
                  onClick={() => copy(window.location.origin + webhookPath, "Webhook URL")}>
                  <Copy className="size-3" /> URL
                </Button>
                <Button variant="outline" size="sm" className="h-6 gap-1 text-[11px]"
                  onClick={() => copy(secret, "Webhook secret")}>
                  <Copy className="size-3" /> Secret
                </Button>
                {project && (
                  <Button variant="outline" size="sm" className="h-6 gap-1 text-[11px]"
                    disabled={busy} onClick={() => save(true)}>
                    <RefreshCw className="size-3" /> Rotate
                  </Button>
                )}
              </div>
            </div>
          )}

          {error && <p className="font-mono text-xs text-destructive sm:col-span-2">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
          <Button disabled={busy || !valid} onClick={() => save(false)}>
            {busy ? "Saving…" : project ? "Save changes" : "Create project"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
