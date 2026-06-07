import { Link, useLocation } from "react-router-dom"
import {
  Activity,
  Bell,
  FolderGit2,
  LayoutDashboard,
  PlayCircle,
  Rocket,
  Settings,
  Timer,
} from "lucide-react"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { useNode } from "@/lib/node-context"
import { UserMenu } from "@/components/user-menu"

const NAV = [
  { title: "Dashboard", url: "/", icon: LayoutDashboard, exact: true },
  { title: "Jobs", url: "/jobs", icon: Activity },
  { title: "Timer Tasks", url: "/tasks", icon: Timer },
  { title: "Run Spider", url: "/schedule", icon: PlayCircle },
  { title: "Deploy", url: "/deploy", icon: Rocket },
  { title: "Projects", url: "/projects", icon: FolderGit2 },
  { title: "Alerts", url: "/alerts", icon: Bell },
]

export function AppSidebar() {
  const location = useLocation()
  const { node } = useNode()

  return (
    <Sidebar collapsible="icon" className="border-r border-sidebar-border">
      <SidebarHeader className="items-center py-4">
        <Link
          to="/"
          className="flex size-9 items-center justify-center rounded-lg bg-primary font-mono text-sm font-bold text-primary-foreground"
          title="ScrapydWeb — Dashboard"
        >
          S
        </Link>
      </SidebarHeader>
      <SidebarContent>
        <SidebarMenu className="items-center gap-1.5 px-2">
          {NAV.map((item) => {
            const active = item.exact
              ? location.pathname === item.url
              : location.pathname.startsWith(item.url)
            return (
              <SidebarMenuItem key={item.title}>
                <SidebarMenuButton
                  asChild
                  isActive={active}
                  tooltip={item.title}
                  className="size-10 justify-center rounded-lg data-[active=true]:bg-sidebar-accent data-[active=true]:text-sidebar-accent-foreground"
                >
                  <Link to={item.url} aria-label={item.title} data-node={node}>
                    <item.icon className="size-5" />
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            )
          })}
        </SidebarMenu>
      </SidebarContent>
      <SidebarFooter className="items-center pb-4">
        <SidebarMenu className="items-center gap-1.5 px-2">
          <SidebarMenuItem>
            <UserMenu />
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton
              asChild
              isActive={location.pathname.startsWith("/settings")}
              tooltip="Settings"
              className="size-10 justify-center rounded-lg"
            >
              <Link to="/settings" aria-label="Settings">
                <Settings className="size-5" />
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}
