# AI Integration Notes

Date: April 29, 2026  
Project: OPD Management System

## Why this document exists

This note captures how AI was actually used during implementation, what it did well, and where human review was essential. The goal is to keep this practical for future work, not theoretical.

## Agent usage

### What AI helped complete

AI was used as an implementation and review partner for:

- performance analysis and documentation
- security review and remediation planning
- Docker and compose setup, optimization, and health checks
- environment-based configuration for development and testing
- operational improvements such as profile-aware commands and Makefile shortcuts

In short, AI was most effective on repetitive engineering tasks, structured audits, and cross-file updates.

### Prompts that worked best

The strongest results came from prompts that were specific and testable. Examples:

- Use Chrome DevTools MCP to analyze application performance and document issues.
- Review code for common security issues and list remediations.
- Implement health check endpoints and make sure compose logs are usable.

What made these effective was clear scope plus clear output expectations.

## MCP server usage

### MCP servers used

- Chrome DevTools MCP
- VS Code workspace tooling for reading/editing/searching and diagnostics

### How MCP helped

Chrome DevTools MCP gave measurable performance data instead of assumptions. Workspace tooling made it possible to apply targeted file edits quickly, then re-check the changed files for issues.

This combination reduced trial-and-error and sped up verification.

## Test generation

### How AI assisted

AI helped generate test ideas from implemented features and from the risk areas identified in review. It also helped shape repeatable test execution flows via compose profiles.

### What it missed

AI did not execute full Docker runtime validation here because Docker CLI was unavailable in this environment. Also, AI suggestions needed manual expansion for:

- concurrency and load edge cases
- environment-specific operational failures
- clinic-specific data quality and workflow edge cases

So AI improved test planning, but final confidence still required human-driven execution.

## Debugging with AI

AI was particularly useful in debugging configuration and orchestration issues, including:

- aligning health checks with readiness and liveness behavior
- fixing logging so container output is visible through compose logs
- resolving compose and Dockerfile mismatches (ports, contexts, startup commands)
- introducing environment- and profile-aware behavior for development and test

The main value was speed in finding and applying consistent multi-file fixes.

## Limitations encountered

### What AI could not do well

- It could not run Docker commands in this session due missing Docker CLI.
- It could not make final production policy decisions (network boundaries, secrets strategy, TLS posture).
- It sometimes produced overly broad documentation unless asked to keep scope tight.

### Where human expertise was critical

- release gating and risk acceptance
- final security and infrastructure decisions
- runtime validation in a real deployment environment

AI accelerated delivery, but did not replace engineering ownership.

## Practical takeaways

- Use AI for structured implementation and review tasks.
- Write prompts with explicit scope and acceptance criteria.
- Keep humans responsible for final validation and production decisions.
- Treat AI output as a draft to verify, not a final authority.
