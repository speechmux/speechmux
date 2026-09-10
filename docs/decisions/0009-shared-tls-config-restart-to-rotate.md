# 0009 — One TLS config for all three ports, loaded once at startup

Status: Accepted

## Context

Core listens on three ports: gRPC, HTTP and WebSocket. Browser `getUserMedia` requires a
secure context, and any ingress in front of Core expects TLS. Certificates also expire and
have to be rotated.

## Decision

`config.BuildTLSConfig` loads the `tls.cert_file` / `tls.key_file` pair once in
`Application.New()` and produces one `*tls.Config` (TLS 1.2 minimum) shared by all three
servers. HTTP and WebSocket wrap their listener with `tls.NewListener(rawLis, tlsCfg)`
rather than calling `ServeTLS(lis, certFile, keyFile)`; gRPC uses
`grpc.Creds(credentials.NewTLS(tlsCfg))`. `srv.TLSConfig` is still set on the
`http.Server` so Go enables HTTP/2 ALPN.

Configuration reload (SIGHUP or `/admin/reload`) does **not** re-read the certificate.
Rotation is a restart.

## Rationale

- `BuildTLSConfig` has already read the files; passing paths back into `ServeTLS` would
  re-read from disk or thread file paths through the API for no benefit. It is also more
  testable — a test can inject an in-memory config with no filesystem.
- Hot-swapping a certificate mid-flight requires coordinating which connections see which
  cert. Restarting with the existing 30 s graceful drain is simple and matches the cadence
  of 90-day and annual renewals.
- A single certificate matches the deployment reality: all three ports are the same host.

## Consequences

- Rotation is `SIGTERM` + start, relying on `server.shutdown_drain_sec` to keep existing
  sessions alive. Automated short-lived certificates would need a restart loop or an
  external terminator.
- Per-port certificates are not supported. If they become necessary, a `ServerName` map on
  `TLSConfig` is the extension point.
- `tls.tls_required: true` without a cert/key pair fails validation at startup rather than
  silently serving plaintext.
- In the Tailscale setup, TLS is terminated by Tailscale and Core stays plaintext, so
  `tls.*` is off there by design.
