import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Check, Copy, KeyRound, Plus, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { api, type ApiToken } from "@/lib/api"
import { fmtDateTime } from "@/lib/datetime"
import { useConfirm } from "@/components/confirm-dialog"

export default function TokensPage() {
  const qc = useQueryClient()
  const { confirm, dialog } = useConfirm()
  const [name, setName] = React.useState("")
  const [fresh, setFresh] = React.useState<string | null>(null)
  const [copied, setCopied] = React.useState(false)

  const { data } = useQuery({ queryKey: ["tokens"], queryFn: api.listTokens })
  const tokens = data?.tokens ?? []

  const create = useMutation({
    mutationFn: () => api.createToken(name.trim()),
    onSuccess: (res) => {
      if (res.status === "ok" && res.plaintext) {
        setFresh(res.plaintext)
        setName("")
        setCopied(false)
        qc.invalidateQueries({ queryKey: ["tokens"] })
      } else {
        toast.error(res.message || "Create failed")
      }
    },
    onError: (e) => toast.error(`Create failed: ${e.message}`),
  })

  const remove = async (t: ApiToken) => {
    if (
      await confirm({
        title: `Revoke token "${t.name}"?`,
        description: "Any script using it will stop working immediately.",
        confirmLabel: "Revoke",
        destructive: true,
      })
    ) {
      await api.deleteToken(t.id)
      qc.invalidateQueries({ queryKey: ["tokens"] })
    }
  }

  const copy = () => {
    if (fresh) {
      navigator.clipboard.writeText(fresh)
      setCopied(true)
      toast.success("Token copied")
    }
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <KeyRound className="size-5" /> API Tokens
        </h2>
        <span className="font-mono text-xs text-muted-foreground">{tokens.length} active</span>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Generate a token</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex gap-2">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="token name (e.g. cron-runner)"
              onKeyDown={(e) => e.key === "Enter" && name.trim() && create.mutate()}
            />
            <Button disabled={!name.trim() || create.isPending} onClick={() => create.mutate()}>
              <Plus className="size-4" /> Generate
            </Button>
          </div>

          {fresh && (
            <div className="flex flex-col gap-2 rounded-lg border border-primary/40 bg-primary/5 p-3">
              <p className="text-xs text-muted-foreground">
                Copy it now — it won't be shown again.
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 overflow-auto rounded bg-background/70 px-2 py-1.5 font-mono text-xs">
                  {fresh}
                </code>
                <Button variant="outline" size="sm" onClick={copy}>
                  {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                  {copied ? "Copied" : "Copy"}
                </Button>
              </div>
            </div>
          )}

          <div className="rounded-lg bg-background/60 p-2.5">
            <p className="mb-1 text-[11px] text-muted-foreground">Use it in curl:</p>
            <pre className="overflow-auto font-mono text-[11px] leading-relaxed">
              {`curl -H 'Authorization: Bearer ${fresh ?? "sdw_…"}' \\\n  '${window.location.origin}/api/groups'`}
            </pre>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Active tokens</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {tokens.length === 0 && (
            <p className="py-4 text-center text-sm text-muted-foreground">No tokens yet.</p>
          )}
          {tokens.map((t) => (
            <div
              key={t.id}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-border bg-secondary/20 px-3 py-2"
            >
              <span className="font-medium">{t.name}</span>
              <code className="font-mono text-xs text-muted-foreground">{t.prefix}</code>
              <span className="font-mono text-[11px] text-muted-foreground">
                created {fmtDateTime(t.created_at)}
                {t.last_used_at ? ` · last used ${fmtDateTime(t.last_used_at)}` : " · never used"}
              </span>
              <Button
                variant="ghost"
                size="icon"
                className="ml-auto size-7 text-destructive hover:text-destructive"
                onClick={() => remove(t)}
                aria-label="Revoke"
              >
                <Trash2 className="size-3.5" />
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>

      {dialog}
    </div>
  )
}
