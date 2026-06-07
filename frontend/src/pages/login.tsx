import * as React from "react"
import { useNavigate } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Lock, UserPlus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api } from "@/lib/api"

export default function LoginPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { data: me } = useQuery({ queryKey: ["auth-me"], queryFn: api.authMe })
  const setupMode = me?.setup_required ?? false

  const [username, setUsername] = React.useState("")
  const [password, setPassword] = React.useState("")
  const [confirm, setConfirm] = React.useState("")
  const [error, setError] = React.useState("")
  const [busy, setBusy] = React.useState(false)

  React.useEffect(() => {
    if (me?.authenticated) navigate("/", { replace: true })
  }, [me, navigate])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    if (setupMode && password !== confirm) {
      setError("Passwords do not match")
      return
    }
    setBusy(true)
    try {
      const res = setupMode
        ? await api.setup(username, password)
        : await api.login(username, password)
      if (res.status === "ok") {
        await qc.invalidateQueries({ queryKey: ["auth-me"] })
        navigate("/", { replace: true })
      } else {
        setError(res.message ?? "Authentication failed")
      }
    } catch (err) {
      setError(String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <div className="mx-auto flex size-12 items-center justify-center rounded-xl bg-primary font-mono text-lg font-bold text-primary-foreground">
            S
          </div>
          <CardTitle className="text-lg">
            {setupMode ? "Create admin account" : "Sign in to ScrapydWeb"}
          </CardTitle>
          {setupMode && (
            <p className="text-xs text-muted-foreground">
              First run — choose the credentials that will protect this instance.
            </p>
          )}
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="flex flex-col gap-4">
            <div className="grid gap-2">
              <Label htmlFor="lg-user">Username</Label>
              <Input
                id="lg-user"
                autoFocus
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="lg-pass">Password</Label>
              <Input
                id="lg-pass"
                type="password"
                autoComplete={setupMode ? "new-password" : "current-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              {setupMode && (
                <p className="text-[11px] text-muted-foreground">At least 8 characters.</p>
              )}
            </div>
            {setupMode && (
              <div className="grid gap-2">
                <Label htmlFor="lg-confirm">Confirm password</Label>
                <Input
                  id="lg-confirm"
                  type="password"
                  autoComplete="new-password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                />
              </div>
            )}
            {error && <p className="font-mono text-xs text-destructive">{error}</p>}
            <Button type="submit" disabled={busy || !username || !password} className="gap-1.5">
              {setupMode ? <UserPlus className="size-4" /> : <Lock className="size-4" />}
              {busy ? "…" : setupMode ? "Create account" : "Sign in"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
