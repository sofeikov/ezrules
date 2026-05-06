# Charter: Navigation And Session Resilience

## Persona

Busy analyst moving quickly across the app.

## Mission

Explore whether navigation, refresh, back/forward, and session behavior preserve a coherent product state.

## Goals

- Navigate between list, detail, create, settings, audit, dashboard, and Tested Events.
- Use browser refresh and back/forward after mutations.
- Let forms partially fill, navigate away, and return.
- Test logout/login and forbidden route behavior.

## Hunt For

- Stale state after refresh or back navigation.
- Broken deep links.
- Session expiry causing data loss without warning.
- Sidebar or breadcrumbs pointing to wrong state.
- Unauthorized routes briefly exposing data.

## Suggested Deterministic Follow-Up

Playwright app-shell/session E2E.
