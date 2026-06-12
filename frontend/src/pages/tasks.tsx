import * as React from "react"
import { Link, useNavigate } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  CalendarClock,
  ListTree,
  Pause,
  Pencil,
  Play,
  Plus,
  Trash2,
  Zap,
} from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { StatusPill } from "@/components/status-pill"
import { api, type TaskRow } from "@/lib/api"
import { fmtDateTime } from "@/lib/datetime"
import { useNode } from "@/lib/node-context"
import { useConfirm } from "@/components/confirm-dialog"

const PILL: Record<TaskRow["status"], { cls: string; label: string }> = {
  Running: { cls: "run", label: "RUNNING" },
  Paused: { cls: "pend", label: "PAUSED" },
  Finished: { cls: "fin", label: "FINISHED" },
}

export default function TasksPage() {
  const { node } = useNode()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { confirm: confirmDialog, dialog: confirmUI } = useConfirm()
  const showHistory = (t: TaskRow) => navigate(`/jobs?q=task_${t.id}_`)

  const { data, isLoading } = useQuery({
    queryKey: ["tasks", node],
    queryFn: () => api.tasks(node),
    refetchInterval: 15_000,
  })

  const act = useMutation({
    mutationFn: ({ action, taskId }: { action: string; taskId?: number; verb: string }) =>
      api.taskAction(node, action, taskId),
    onSuccess: (res, { verb }) => {
      const ok = (res as { status?: string }).status === "ok"
      if (ok) toast.success(verb)
      else toast.error(`${verb} failed: ${JSON.stringify(res).slice(0, 200)}`)
      qc.invalidateQueries({ queryKey: ["tasks", node] })
    },
    onError: (err, { verb }) => toast.error(`${verb} failed: ${err.message}`),
  })

  if (isLoading)
    return (
      <div className="mx-auto max-w-7xl">
        <Skeleton className="h-96 rounded-xl" />
      </div>
    )

  const tasks = data?.tasks ?? []
  const schedulerOn = data?.scheduler_enabled ?? true

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">Timer Tasks</h2>
        <span className="font-mono text-xs text-muted-foreground">{data?.total ?? 0} tasks</span>
        <Button asChild size="sm" className="ml-auto h-8 gap-1.5">
          <Link to="/schedule?timer=1">
            <Plus className="size-3.5" /> New task
          </Link>
        </Button>
        <label className="flex items-center gap-2 rounded-lg border border-border bg-secondary/40 px-3 py-1.5">
          <span
            className={
              schedulerOn
                ? "size-2 rounded-full bg-primary"
                : "size-2 rounded-full bg-destructive"
            }
          />
          <span className="text-xs font-medium">
            Scheduler {schedulerOn ? "running" : "paused"}
          </span>
          <Switch
            checked={schedulerOn}
            onCheckedChange={(on) =>
              act.mutate({
                action: on ? "enable" : "disable",
                verb: on ? "Scheduler resumed" : "Scheduler paused",
              })
            }
          />
        </label>
      </div>

      <Card className="py-0">
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                {["ID", "Status", "Name", "Project / Spider", "Trigger", "Next run", "Runs", "Prev result", ""].map(
                  (h, i) => (
                    <TableHead
                      key={i}
                      className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground"
                    >
                      {h}
                    </TableHead>
                  ),
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {tasks.length === 0 && (
                <TableRow>
                  <TableCell colSpan={9} className="py-10 text-center text-muted-foreground">
                    No timer tasks yet — create one from the Run Spider page.
                  </TableCell>
                </TableRow>
              )}
              {tasks.map((t) => {
                const pill = PILL[t.status]
                return (
                  <TableRow key={t.id} className="hover:bg-secondary/30">
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {t.id}
                    </TableCell>
                    <TableCell>
                      <StatusPill status={pill.cls} label={pill.label} />
                    </TableCell>
                    <TableCell className="max-w-40 truncate font-medium">
                      {t.name || <span className="text-muted-foreground">—</span>}
                    </TableCell>
                    <TableCell>
                      <span className="font-mono text-xs">
                        {t.project} / <span className="text-foreground">{t.spider}</span>
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="font-mono text-[10px]">
                        <CalendarClock className="size-3" />
                        {triggerSummary(t)}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {fmtDateTime(t.next_run_time)}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {t.run_times}
                      {t.fail_times > 0 && (
                        <span className="text-destructive"> ({t.fail_times} fail)</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <span
                        className={
                          t.prev_run_result.startsWith("FAIL")
                            ? "font-mono text-xs text-destructive"
                            : "font-mono text-xs text-muted-foreground"
                        }
                      >
                        {t.prev_run_result}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Act
                          label="Run history"
                          icon={ListTree}
                          onClick={() => showHistory(t)}
                        />
                        <Act
                          label="Edit task"
                          icon={Pencil}
                          onClick={() => navigate(`/schedule?timer=1&taskId=${t.id}`)}
                        />
                        {t.status !== "Finished" && (
                          <Act
                            label="Fire now"
                            icon={Zap}
                            onClick={() =>
                              act.mutate({ action: "fire", taskId: t.id, verb: `Task #${t.id} fired` })
                            }
                          />
                        )}
                        {t.status === "Running" && (
                          <Act
                            label="Pause"
                            icon={Pause}
                            onClick={() =>
                              act.mutate({ action: "pause", taskId: t.id, verb: `Task #${t.id} paused` })
                            }
                          />
                        )}
                        {t.status === "Paused" && (
                          <Act
                            label="Resume"
                            icon={Play}
                            onClick={() =>
                              act.mutate({ action: "resume", taskId: t.id, verb: `Task #${t.id} resumed` })
                            }
                          />
                        )}
                        {t.status === "Finished" ? (
                          <Act
                            label="Delete"
                            icon={Trash2}
                            destructive
                            onClick={async () =>
                              (await confirmDialog({
                                title: `Delete task #${t.id}?`,
                                description: "The task and all of its run results will be removed.",
                                confirmLabel: "Delete",
                                destructive: true,
                              })) &&
                              act.mutate({ action: "delete", taskId: t.id, verb: `Task #${t.id} deleted` })
                            }
                          />
                        ) : (
                          <Act
                            label="Stop (remove from scheduler)"
                            icon={Trash2}
                            destructive
                            onClick={async () =>
                              (await confirmDialog({
                                title: `Stop task #${t.id}?`,
                                description: "It will be removed from the scheduler and no longer fire.",
                                confirmLabel: "Stop task",
                                destructive: true,
                              })) &&
                              act.mutate({ action: "remove", taskId: t.id, verb: `Task #${t.id} stopped` })
                            }
                          />
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {confirmUI}
    </div>
  )
}

function triggerSummary(t: TaskRow) {
  if (t.trigger === "cron") {
    const dow = t.day_of_week && t.day_of_week !== "*" ? ` dow=${t.day_of_week}` : ""
    return `cron ${t.minute} ${t.hour} ${t.day} ${t.month}${dow}`
  }
  return t.trigger
}

function Act({
  label,
  icon: Icon,
  onClick,
  destructive,
}: {
  label: string
  icon: React.ElementType
  onClick: () => void
  destructive?: boolean
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className={destructive ? "size-7 text-destructive hover:text-destructive" : "size-7"}
          onClick={onClick}
          aria-label={label}
        >
          <Icon className="size-3.5" />
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}
