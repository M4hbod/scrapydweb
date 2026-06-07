import * as React from "react"
import { useParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { FileCode2 } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"

export default function CodePage() {
  const { project, version } = useParams()
  const [selected, setSelected] = React.useState<string | null>(null)

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

  // auto-select first spider file
  React.useEffect(() => {
    if (selected || !files.length) return
    const spider = files.find((f) => f.path.includes("spiders/") && f.path.endsWith(".py"))
    setSelected((spider ?? files[0]).path)
  }, [files, selected])

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
          <Card className="h-fit py-2 md:sticky md:top-20">
            <CardContent className="px-2">
              <ScrollArea className="max-h-[70vh]">
                <div className="flex flex-col">
                  {files.map((f) => (
                    <button
                      key={f.path}
                      onClick={() => setSelected(f.path)}
                      className={cn(
                        "flex items-center gap-2 rounded-md px-2 py-1.5 text-left font-mono text-xs transition-colors",
                        selected === f.path
                          ? "bg-secondary text-foreground"
                          : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground",
                      )}
                    >
                      <FileCode2 className="size-3.5 shrink-0" />
                      <span className="truncate">{f.path}</span>
                    </button>
                  ))}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>

          <Card className="min-w-0 gap-0 py-0">
            <CardContent className="px-0">
              <div className="border-b border-border px-4 py-2 font-mono text-xs text-muted-foreground">
                {selected ?? "select a file"}
              </div>
              {fileLoading ? (
                <Skeleton className="m-4 h-64 rounded-lg" />
              ) : file?.status === "ok" ? (
                <pre className="max-h-[70vh] overflow-auto px-0 py-3 font-mono text-xs leading-relaxed">
                  {(file.text ?? "").split("\n").map((line, i) => (
                    <span key={i} className="block px-4 hover:bg-secondary/30">
                      <span className="mr-4 inline-block w-8 select-none text-right text-muted-foreground/50">
                        {i + 1}
                      </span>
                      {line}
                    </span>
                  ))}
                </pre>
              ) : (
                <p className="px-4 py-8 text-center text-sm text-muted-foreground">
                  {file?.message ?? "—"}
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
