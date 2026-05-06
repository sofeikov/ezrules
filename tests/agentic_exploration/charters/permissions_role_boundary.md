# Charter: Permissions And Role Boundaries

## Persona

Operations admin managing least-privilege access.

## Mission

Explore whether users can only see and do what their roles allow.

## Goals

- Try rule create/edit/promote with insufficient permissions.
- Grant and revoke permissions, then retry without changing the user identity.
- Check direct navigation to forbidden pages.
- Check API behavior for forbidden actions if API access is available.
- Confirm UI hides or disables actions consistently.

## Hunt For

- Forbidden buttons visible and executable.
- UI denies but API allows.
- Permission changes not taking effect until logout without explanation.
- Read-only users mutating state through secondary workflows.
- Missing 403 messaging or confusing redirects.

## Suggested Deterministic Follow-Up

Backend permission journey plus Playwright role-boundary E2E.
