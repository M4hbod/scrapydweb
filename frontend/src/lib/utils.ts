import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// A finished run (status "2") counts as FAILED only for genuine error/abort reasons.
// Everything else — "finished" and deliberate stops (pagecount_limit, subscription_required,
// CLOSESPIDER_*) — is a success. Mirrors the Prometheus exporter's _FAILED_REASONS.
export const FAILED_FINISH_REASONS = new Set([
  "cancelled",
  "shutdown",
  "closespider_errorcount",
  "memusage_exceeded",
  "error",
])

export function isFailedReason(reason: string | null | undefined): boolean {
  return !!reason && reason !== "N/A" && FAILED_FINISH_REASONS.has(reason)
}
