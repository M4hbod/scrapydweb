import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { api, type NodeInfo } from "@/lib/api"

interface NodeContextValue {
  node: number
  setNode: (node: number) => void
  nodes: NodeInfo[]
}

const NodeContext = React.createContext<NodeContextValue>({
  node: 1,
  setNode: () => {},
  nodes: [],
})

export function NodeProvider({ children }: { children: React.ReactNode }) {
  const [node, setNodeState] = React.useState<number>(() => {
    const saved = Number(localStorage.getItem("scrapydweb.node"))
    return Number.isInteger(saved) && saved >= 1 ? saved : 1
  })
  const { data } = useQuery({ queryKey: ["nodes"], queryFn: api.nodes, staleTime: 60_000 })
  const nodes = data?.nodes ?? []

  const setNode = React.useCallback((n: number) => {
    localStorage.setItem("scrapydweb.node", String(n))
    setNodeState(n)
  }, [])

  // clamp if the saved node no longer exists
  React.useEffect(() => {
    if (nodes.length && !nodes.some((n) => n.node === node)) setNode(1)
  }, [nodes, node, setNode])

  return <NodeContext.Provider value={{ node, setNode, nodes }}>{children}</NodeContext.Provider>
}

export function useNode() {
  return React.useContext(NodeContext)
}
