export function sessionFetch(
  sessionId: string,
  url: string,
  options: RequestInit = {},
) {
  const headers = new Headers(options.headers);
  headers.set("X-EduMind-Session", sessionId);
  return window.fetch(url, { ...options, headers });
}

export function fileUrl(sessionId: string, filename: string, inline = false) {
  return `/api/v1/files/${encodeURIComponent(filename)}?session_id=${encodeURIComponent(sessionId)}${inline ? "&inline=true" : ""}`;
}
