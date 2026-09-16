export const FRONTEND_HOST_HEADER = "x-deeptutor-frontend-host";

const UNTRUSTED_FORWARD_HEADERS = [
  "connection",
  "forwarded",
  "x-forwarded-host",
  "x-forwarded-proto",
  "x-forwarded-for",
  "x-forwarded-port",
  "x-forwarded-server",
  "x-real-ip",
  "x-client-ip",
  "x-host",
  "x-original-host",
  FRONTEND_HOST_HEADER,
];

export function prepareBackendForwardHeaders(
  source: Headers,
  frontendHost: string,
): Headers {
  const headers = new Headers(source);
  const connectionTokens = (headers.get("connection") || "")
    .split(",")
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);

  for (const name of [...UNTRUSTED_FORWARD_HEADERS, ...connectionTokens]) {
    headers.delete(name);
  }
  headers.set(FRONTEND_HOST_HEADER, frontendHost);
  return headers;
}
