import * as React from "react"
import { useParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import {
  ChevronDown,
  ChevronRight,
  FileCode2,
  FileText,
  Folder,
  FolderOpen,
} from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"

interface TreeNode {
  name: string
  path: string
  dir: boolean
  children: TreeNode[]
}

function buildTree(paths: string[]): TreeNode[] {
  const root: TreeNode = { name: "", path: "", dir: true, children: [] }
  for (const path of paths) {
    const parts = path.split("/")
    let cur = root
    parts.forEach((part, i) => {
      const isLeaf = i === parts.length - 1
      const p = parts.slice(0, i + 1).join("/")
      let child = cur.children.find((c) => c.name === part)
      if (!child) {
        child = { name: part, path: p, dir: !isLeaf, children: [] }
        cur.children.push(child)
      }
      cur = child
    })
  }
  const sortRec = (n: TreeNode) => {
    n.children.sort((a, b) =>
      a.dir !== b.dir ? (a.dir ? -1 : 1) : a.name.localeCompare(b.name),
    )
    n.children.forEach(sortRec)
  }
  sortRec(root)
  return root.children
}

function collectDirs(nodes: TreeNode[], acc: Set<string>) {
  for (const n of nodes) {
    if (n.dir) {
      acc.add(n.path)
      collectDirs(n.children, acc)
    }
  }
  return acc
}

function fileIcon(name: string) {
  return name.endsWith(".py") ? FileCode2 : FileText
}

function Tree({
  nodes,
  depth,
  selected,
  onSelect,
  expanded,
  toggle,
}: {
  nodes: TreeNode[]
  depth: number
  selected: string | null
  onSelect: (p: string) => void
  expanded: Set<string>
  toggle: (p: string) => void
}) {
  return (
    <>
      {nodes.map((n) => {
        const pad = { paddingLeft: `${depth * 12 + 8}px` }
        if (n.dir) {
          const open = expanded.has(n.path)
          const FolderIcon = open ? FolderOpen : Folder
          const Chevron = open ? ChevronDown : ChevronRight
          return (
            <React.Fragment key={n.path}>
              <button
                type="button"
                onClick={() => toggle(n.path)}
                style={pad}
                className="flex w-full items-center gap-1 py-1 pr-2 text-left font-mono text-xs text-foreground/80 transition-colors hover:bg-secondary/50"
              >
                <Chevron className="size-3.5 shrink-0 text-muted-foreground" />
                <FolderIcon className="size-3.5 shrink-0 text-chart-3" />
                <span className="truncate">{n.name}</span>
              </button>
              {open && (
                <Tree
                  nodes={n.children}
                  depth={depth + 1}
                  selected={selected}
                  onSelect={onSelect}
                  expanded={expanded}
                  toggle={toggle}
                />
              )}
            </React.Fragment>
          )
        }
        const Icon = fileIcon(n.name)
        const active = selected === n.path
        return (
          <button
            key={n.path}
            type="button"
            onClick={() => onSelect(n.path)}
            style={pad}
            className={cn(
              "flex w-full items-center gap-1.5 py-1 pr-2 text-left font-mono text-xs transition-colors",
              active
                ? "bg-primary/15 text-primary"
                : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground",
            )}
          >
            {/* spacer to align with folder chevrons */}
            <span className="size-3.5 shrink-0" />
            <Icon className="size-3.5 shrink-0 text-muted-foreground" />
            <span className="truncate">{n.name}</span>
          </button>
        )
      })}
    </>
  )
}

export default function CodePage() {
  const { project, version } = useParams()
  const [selected, setSelected] = React.useState<string | null>(null)
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set())

  const { data: listing, isLoading } = useQuery({
    queryKey: ["code-list", project, version],
    queryFn: () => api.codeList(project!, version!),
  })

  const files = React.useMemo(
    () =>
      (listing?.files ?? []).filter(
        (f) => !f.path.startsWith("EGG-INFO/") || f.path === "EGG-INFO/requires.txt",
      ),
    [listing],
  )
  const tree = React.useMemo(() => buildTree(files.map((f) => f.path)), [files])

  // expand all folders once the listing arrives
  React.useEffect(() => {
    if (tree.length) setExpanded(collectDirs(tree, new Set<string>()))
  }, [tree])

  // auto-select first spider file (else first file)
  React.useEffect(() => {
    if (selected || !files.length) return
    const spider = files.find((f) => f.path.includes("spiders/") && f.path.endsWith(".py"))
    setSelected((spider ?? files[0]).path)
  }, [files, selected])

  const toggle = React.useCallback((p: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(p)) next.delete(p)
      else next.add(p)
      return next
    })
  }, [])

  const { data: file, isLoading: fileLoading } = useQuery({
    queryKey: ["code-file", project, version, selected],
    queryFn: () => api.codeFile(project!, version!, selected!),
    enabled: !!selected,
  })

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <h2 className="text-lg font-semibold">{project}</h2>
        <span className="font-mono text-xs text-muted-foreground">
          version {version} · deployed egg source
        </span>
      </div>

      {isLoading ? (
        <Skeleton className="h-96 rounded-xl" />
      ) : listing?.status !== "ok" ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            {listing?.message ?? "Failed to load the egg."}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-[18rem_1fr]">
          <Card className="h-fit overflow-hidden py-0 md:sticky md:top-20">
            <div className="border-b border-border px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              Explorer
            </div>
            <ScrollArea className="max-h-[72vh]">
              <div className="flex flex-col py-1">
                <Tree
                  nodes={tree}
                  depth={0}
                  selected={selected}
                  onSelect={setSelected}
                  expanded={expanded}
                  toggle={toggle}
                />
              </div>
            </ScrollArea>
          </Card>

          <Card className="min-w-0 gap-0 overflow-hidden py-0">
            <div className="border-b border-border px-4 py-2 font-mono text-xs text-muted-foreground">
              {selected ?? "select a file"}
            </div>
            {fileLoading ? (
              <Skeleton className="m-4 h-64 rounded-lg" />
            ) : file?.status === "ok" ? (
              <pre className="max-h-[72vh] overflow-auto py-3 font-mono text-xs leading-relaxed">
                {(file.text ?? "").split("\n").map((line, i) => (
                  <span key={i} className="flex hover:bg-secondary/30">
                    <span className="mr-4 inline-block w-10 shrink-0 select-none px-2 text-right text-muted-foreground/40">
                      {i + 1}
                    </span>
                    <span className="whitespace-pre pr-4">{line}</span>
                  </span>
                ))}
              </pre>
            ) : (
              <p className="px-4 py-8 text-center text-sm text-muted-foreground">
                {file?.message ?? "—"}
              </p>
            )}
          </Card>
        </div>
      )}
    </div>
  )
}
