import * as React from "react"
import { useNavigate } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { KeyRound, LogOut, UserCircle2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { SidebarMenuButton } from "@/components/ui/sidebar"
import { api } from "@/lib/api"

export function UserMenu() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { data: me } = useQuery({ queryKey: ["auth-me"], queryFn: api.authMe })
  const [pwOpen, setPwOpen] = React.useState(false)

  const logout = async () => {
    await api.logout()
    await qc.invalidateQueries({ queryKey: ["auth-me"] })
    navigate("/login", { replace: true })
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <SidebarMenuButton
            tooltip={me?.username ?? "Account"}
            className="size-10 justify-center rounded-lg"
            aria-label="Account"
          >
            <UserCircle2 className="size-5" />
          </SidebarMenuButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent side="right" align="end" className="w-48">
          <DropdownMenuLabel className="font-mono text-xs">
            {me?.username ?? "…"}
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setPwOpen(true)}>
            <KeyRound className="size-4" /> Change password
          </DropdownMenuItem>
          <DropdownMenuItem variant="destructive" onClick={logout}>
            <LogOut className="size-4" /> Log out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <ChangePasswordDialog open={pwOpen} onOpenChange={setPwOpen} />
    </>
  )
}

function ChangePasswordDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (o: boolean) => void
}) {
  const [current, setCurrent] = React.useState("")
  const [next, setNext] = React.useState("")
  const [confirm, setConfirm] = React.useState("")
  const [error, setError] = React.useState("")
  const [busy, setBusy] = React.useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    if (next !== confirm) {
      setError("Passwords do not match")
      return
    }
    setBusy(true)
    try {
      const res = await api.changePassword(current, next)
      if (res.status === "ok") {
        toast.success("Password changed")
        onOpenChange(false)
        setCurrent("")
        setNext("")
        setConfirm("")
      } else {
        setError(res.message ?? "Failed")
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="text-base">Change password</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <div className="grid gap-2">
            <Label htmlFor="cp-cur">Current password</Label>
            <Input
              id="cp-cur"
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="cp-new">New password</Label>
            <Input
              id="cp-new"
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="cp-confirm">Confirm new password</Label>
            <Input
              id="cp-confirm"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
          </div>
          {error && <p className="font-mono text-xs text-destructive">{error}</p>}
          <Button type="submit" disabled={busy || !current || !next}>
            {busy ? "…" : "Change password"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
