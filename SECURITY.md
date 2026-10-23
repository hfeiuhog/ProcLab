# Security

This is a research prototype. The default server is for loopback use. Enable authentication and distinct credentials for shared deployment; keep stores private and run one API worker.

Use **Security → Report a vulnerability** for private reports when available. Do not put secrets, private documents or account data in public issues. If private reporting is unavailable, request private contact without posting sensitive details.

Include affected commit, sanitized configuration, trust boundary and a minimal synthetic reproduction.

Boundaries to inspect: owner/project isolation, frozen-input binding, tool budgets, guarded SQL, document approval, publication gates, session revocation and recovery.

No independent security audit or production certification is claimed.
