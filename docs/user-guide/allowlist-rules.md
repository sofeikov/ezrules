# Allowlist Rules

Allowlist rules give you an explicit safe-pass lane before the main rule set runs.

If your team still says "whitelist", this is the same concept. The product uses **allowlist** in the UI and API.

## Why Allowlist Rules Exist

Most rule engines are built around escalation:

- suspicious traffic gets `HOLD`
- clearly bad traffic gets `CANCEL`
- everything else falls through

That works until you have traffic that should be treated as explicitly safe before the normal rules even start.

Typical cases:

- trusted internal or partner traffic
- known-good merchants, users, or corridors
- false-positive suppression for patterns you have already reviewed and accepted
- maintenance or replay traffic that should not trigger the main fraud logic

In those cases, a normal rule that returns `RELEASE` is often not enough, because the rest of the rule set still runs and may still produce a more severe outcome.

Allowlist rules solve that by changing control flow, not just outcome names.

## How Allowlist Evaluation Works

For each `POST /api/v2/evaluate` call, ezrules now evaluates in this order:

1. active allowlist rules
2. if none match, the active main rule set
3. shadow and rollout behavior only on the main path

If one or more allowlist rules match:

- the evaluation stops there
- the main rule set is skipped for the returned result
- the response and stored event reflect only the matching allowlist results

This is why allowlist rules are useful. They are not just "rules that return a safe outcome". They are rules that can stop the normal decision flow entirely.

## The Neutral Outcome

Allowlist rules must return the configured neutral outcome.

Current implementation:

- the runtime setting is `neutral_outcome`
- the default value is `RELEASE`
- admins choose it in **Settings** from the existing outcomes catalog
- the setting is available through `GET /api/v2/settings/runtime` and `PUT /api/v2/settings/runtime`

That means the rule editor and API validation both expect allowlist rules to return the currently configured neutral outcome, not an arbitrary outcome.

## When To Use Allowlist vs Main Rules

Use **Main rules** when:

- you want the rule to participate in normal outcome resolution
- you still want other rules to evaluate
- you are expressing ordinary fraud/compliance logic

Use **Allowlist rules** when:

- a match should immediately produce the safe outcome
- you want to suppress the rest of the rule set for that event
- the condition is a policy-level trust decision, not just one more scoring signal

## Create an Allowlist Rule

1. Open **Rules**
2. Click **New Rule**
3. In **Rule Lane**, choose **Allowlist rules**
4. Write logic that returns the configured neutral outcome

Example:

```python
if $merchant_id in @trusted_merchants:
    return 'RELEASE'
```

The editor validates allowlist rules more strictly than main rules. If the configured neutral outcome is `RELEASE`, returning `HOLD` or `CANCEL` will fail validation.

## Edit an Existing Rule Into the Allowlist Lane

You can also move a rule into the allowlist lane from the rule detail page:

1. Open the rule
2. Click **Edit Rule**
3. Change **Rule Lane** to **Allowlist rules**
4. Update logic if needed so it returns the configured neutral outcome
5. Save

The rule detail and rules list views show an `Allowlist` / `ALLOWLIST` badge so these rules stand out from the main rule set.

## How This Differs From Shadow and Rollouts

Allowlist rules are production behavior, not candidate-deployment behavior.

- **Shadow** is for observe-only validation on live traffic
- **Rollouts** are for gradual live exposure of a candidate rule version
- **Allowlist** is a first-class production lane that changes how evaluation works

Because of that, allowlist rules cannot be deployed to shadow or rollout.

## What You See in Responses and Stored Events

When an allowlist rule matches:

- `resolved_outcome` is the configured neutral outcome
- `rule_results` includes the matching allowlist rules only
- the current main rules do not appear in the returned result for that event

This behavior is visible both in the direct evaluator response and in **Tested Events**.

## Operational Guidance

- Keep allowlist rules narrow and auditable
- Prefer maintained lists (`@trusted_users`, `@trusted_merchants`) over hard-coded IDs where possible
- Review allowlist scope regularly, because broad allowlists can silently hide problems from the main rule set
- Use main rules, shadow, and rollouts for experimentation; use allowlist only for policies you are comfortable enforcing immediately

## Related Docs

- [Creating Rules](creating-rules.md)
- [Rule Rollouts](rule-rollouts.md)
- [Shadow Deployment](shadow-deployment.md)
- [Evaluator API](../api-reference/evaluator-api.md)
