# Security Policy

## Scope

BranchRift is designed as a read-only repository inspection tool. It should not modify repository contents or execute user-configured shell commands.

Security-sensitive areas include:

- subprocess argument handling
- Git revision handling
- configuration parsing and validation
- path/rule matching
- terminal and JSON output integrity

## Reporting a vulnerability

Please do not publish exploit details in a public issue. Use GitHub Private Vulnerability Reporting when it is enabled for the repository.

A useful report should include the affected version, reproduction steps, expected behavior, actual behavior, and the security impact.

## Supported version

Only the latest published version is supported.
