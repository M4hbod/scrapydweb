import * as React from "react"
import { Navigate, Route, Routes, useLocation } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { Card, CardContent } from "@/components/ui/card"
import { Layout } from "@/components/layout"
import DashboardPage from "@/pages/dashboard"
import LoginPage from "@/pages/login"
import JobsPage from "@/pages/jobs"
import TasksPage from "@/pages/tasks"
import LogPage from "@/pages/log"
import SchedulePage from "@/pages/schedule"
import GroupPage from "@/pages/group"
import TokensPage from "@/pages/tokens"
import DeployPage from "@/pages/deploy"
import CodePage from "@/pages/code"
import ProjectsPage from "@/pages/projects"
import AlertsPage from "@/pages/alerts"
import SettingsPage from "@/pages/settings"

export default function App() {
  return (
    <Routes>
      <Route path="login" element={<LoginPage />} />
      <Route
        element={
          <AuthGate>
            <Layout />
          </AuthGate>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="jobs" element={<JobsPage />} />
        <Route path="log/:node/:opt/:project/:spider/:job" element={<LogPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="schedule" element={<SchedulePage />} />
        <Route path="group" element={<GroupPage />} />
        <Route path="tokens" element={<TokensPage />} />
        <Route path="deploy" element={<DeployPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="code/:project/:version" element={<CodePage />} />
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}

function AuthGate({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const { data: me, isLoading } = useQuery({
    queryKey: ["auth-me"],
    queryFn: api.authMe,
    staleTime: 60_000,
  })
  if (isLoading) return null
  if (me && !me.authenticated)
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <>{children}</>
}

function NotFound() {
  return (
    <Card className="mx-auto max-w-3xl">
      <CardContent className="py-16 text-center">
        <h2 className="text-lg font-semibold">404</h2>
        <p className="text-sm text-muted-foreground">Page not found.</p>
      </CardContent>
    </Card>
  )
}
