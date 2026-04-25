# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest (`main`) | ✅ |
| older tags | ❌ — please upgrade |

## Reporting a Vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.**

To report a security issue, send an email to:

**security@[your-domain]** _(or use [GitHub private vulnerability reporting](https://github.com/enesbakis/OpenCS2/security/advisories/new))_

Include:
- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fix (optional)

We aim to acknowledge reports within **48 hours** and provide a fix within **14 days** for confirmed issues.

## Scope

Issues in scope:
- Remote code execution
- Authentication bypass
- Privilege escalation
- Sensitive data exposure (credentials, tokens)
- SSRF, XXE, SQLi, XSS within the panel

Out of scope:
- Vulnerabilities in CS2 itself (report to Valve)
- Issues requiring physical access to the server
- Self-XSS

## Disclosure Policy

We follow [responsible disclosure](https://en.wikipedia.org/wiki/Responsible_disclosure).  
We will credit reporters in the release notes unless anonymity is requested.
