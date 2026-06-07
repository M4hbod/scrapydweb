// Curated catalog of Scrapy settings for the Run Spider page.
// Keys must match the backend validator: ^[A-Z][A-Z0-9_]{0,30}$
// Dict-typed settings (DEFAULT_REQUEST_HEADERS, ITEM_PIPELINES, ...) are
// excluded — they cannot be expressed as KEY=VALUE via schedule.json.

export type SettingType = "bool" | "int" | "float" | "str" | "enum"

export interface ScrapySettingDef {
  key: string
  type: SettingType
  default: string
  description: string
  options?: string[]
  presets?: { label: string; value: string }[]
}

// UA strings mirror the backend's legacy UA_DICT (vars.py)
const UA_PRESETS = [
  {
    label: "Chrome",
    value:
      "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.109 Safari/537.36",
  },
  {
    label: "iPhone",
    value:
      "Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/604.1.38 (KHTML, like Gecko) Version/11.0 Mobile/15A372 Safari/604.1",
  },
  {
    label: "iPad",
    value:
      "Mozilla/5.0 (iPad; CPU OS 12_1_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.0 Mobile/15E148 Safari/604.1",
  },
  {
    label: "Android",
    value:
      "Mozilla/5.0 (Linux; Android 8.0.0; Pixel 2 XL Build/OPD1.170816.004) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.109 Mobile Safari/537.36",
  },
]

export const SCRAPY_SETTINGS: ScrapySettingDef[] = [
  // --- crawling behavior
  { key: "USER_AGENT", type: "str", default: "Scrapy/x.y", description: "User-Agent header for requests", presets: UA_PRESETS },
  { key: "ROBOTSTXT_OBEY", type: "bool", default: "True", description: "Respect robots.txt policies" },
  { key: "COOKIES_ENABLED", type: "bool", default: "True", description: "Enable the cookies middleware" },
  { key: "COOKIES_DEBUG", type: "bool", default: "False", description: "Log all cookies sent/received" },
  { key: "DEPTH_LIMIT", type: "int", default: "0", description: "Max crawl depth (0 = no limit)" },
  { key: "URLLENGTH_LIMIT", type: "int", default: "2083", description: "Max URL length to crawl" },
  { key: "REFERER_ENABLED", type: "bool", default: "True", description: "Populate the Referer header" },
  { key: "AJAXCRAWL_ENABLED", type: "bool", default: "False", description: "Discover AJAX-crawlable pages" },
  // --- concurrency & throttling
  { key: "CONCURRENT_REQUESTS", type: "int", default: "16", description: "Max concurrent requests (global)" },
  { key: "CONCURRENT_REQUESTS_PER_DOMAIN", type: "int", default: "8", description: "Max concurrent requests per domain" },
  { key: "CONCURRENT_REQUESTS_PER_IP", type: "int", default: "0", description: "Max concurrent requests per IP (0 = per-domain rules)" },
  { key: "CONCURRENT_ITEMS", type: "int", default: "100", description: "Max items processed concurrently in pipelines" },
  { key: "DOWNLOAD_DELAY", type: "float", default: "0", description: "Seconds to wait between requests to the same site" },
  { key: "RANDOMIZE_DOWNLOAD_DELAY", type: "bool", default: "True", description: "Randomize delay (0.5–1.5 × DOWNLOAD_DELAY)" },
  { key: "AUTOTHROTTLE_ENABLED", type: "bool", default: "False", description: "Auto-adjust delay from server load" },
  { key: "AUTOTHROTTLE_START_DELAY", type: "float", default: "5.0", description: "Initial download delay for AutoThrottle" },
  { key: "AUTOTHROTTLE_MAX_DELAY", type: "float", default: "60.0", description: "Max download delay under high latency" },
  { key: "AUTOTHROTTLE_TARGET_CONCURRENCY", type: "float", default: "1.0", description: "Average parallel requests per remote site" },
  { key: "AUTOTHROTTLE_DEBUG", type: "bool", default: "False", description: "Log every AutoThrottle adjustment" },
  // --- downloader
  { key: "DOWNLOAD_TIMEOUT", type: "int", default: "180", description: "Downloader timeout in seconds" },
  { key: "DOWNLOAD_MAXSIZE", type: "int", default: "1073741824", description: "Max response size in bytes (0 = no limit)" },
  { key: "DOWNLOAD_FAIL_ON_DATALOSS", type: "bool", default: "True", description: "Fail on broken/truncated responses" },
  { key: "DNS_TIMEOUT", type: "int", default: "60", description: "DNS query timeout in seconds" },
  { key: "RETRY_ENABLED", type: "bool", default: "True", description: "Retry failed requests" },
  { key: "RETRY_TIMES", type: "int", default: "2", description: "Max retries per request (besides the first attempt)" },
  { key: "RETRY_PRIORITY_ADJUST", type: "int", default: "-1", description: "Priority shift applied to retried requests" },
  { key: "REDIRECT_ENABLED", type: "bool", default: "True", description: "Follow HTTP redirects" },
  { key: "REDIRECT_MAX_TIMES", type: "int", default: "20", description: "Max redirects per request" },
  { key: "HTTPCACHE_ENABLED", type: "bool", default: "False", description: "Cache responses on disk (HTTP cache middleware)" },
  // --- stopping conditions
  { key: "CLOSESPIDER_TIMEOUT", type: "int", default: "0", description: "Close the spider after N seconds (0 = never)" },
  { key: "CLOSESPIDER_PAGECOUNT", type: "int", default: "0", description: "Close after N responses crawled" },
  { key: "CLOSESPIDER_ITEMCOUNT", type: "int", default: "0", description: "Close after N items scraped" },
  { key: "CLOSESPIDER_ERRORCOUNT", type: "int", default: "0", description: "Close after N errors" },
  // --- output & logging
  { key: "LOG_LEVEL", type: "enum", default: "DEBUG", description: "Minimum log severity", options: ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] },
  { key: "LOGSTATS_INTERVAL", type: "float", default: "60.0", description: "Seconds between crawl-stats log lines" },
  { key: "FEED_EXPORT_ENCODING", type: "str", default: "utf-8 (json: ascii)", description: "Encoding for exported feeds" },
  { key: "JOBDIR", type: "str", default: "", description: "Directory for pausing/resuming crawl state" },
  // --- resources
  { key: "MEMUSAGE_LIMIT_MB", type: "int", default: "0", description: "Kill the spider above this RSS memory (MB, 0 = off)" },
  { key: "REACTOR_THREADPOOL_MAXSIZE", type: "int", default: "10", description: "Twisted thread-pool size (DNS, IO)" },
  { key: "TELNETCONSOLE_ENABLED", type: "bool", default: "True", description: "Enable the telnet debug console" },
]

export const SETTINGS_BY_KEY = new Map(SCRAPY_SETTINGS.map((s) => [s.key, s]))

export const SETTING_KEY_RE = /^[A-Z][A-Z0-9_]{0,30}$/
export const ARG_KEY_RE = /^[A-Za-z_][A-Za-z0-9_]*$/
// args land as top-level scrapyd POST keys — these must not be overridden
export const RESERVED_ARG_KEYS = new Set([
  "project",
  "_version",
  "spider",
  "jobid",
  "setting",
  "filename",
  "checked_amount",
])
