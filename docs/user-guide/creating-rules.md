# Creating Rules

Learn how to write effective business rules in ezrules.

---

## Rule Structure

Rules are Python functions that evaluate events and return boolean values:

```python
def evaluate_event(event):
    # Your logic here
    if condition:
        return True  # Trigger outcome
    return False     # No action
```

---

## Accessing Event Data

Access event attributes using the `$` notation:

```python
# Access transaction attributes
if $amount > 10000:
    return True

# Use in assignments
user_country = $country
is_high_risk = $amount > 5000 and $country in @high_risk_countries
```

---

## Common Rule Patterns

### Threshold Rules

```python
# Simple threshold
if $amount > 10000:
    return True
```

### List-Based Rules

```python
# Check against blocklist
if $user_id in @blocked_users:
    return True
```

### Velocity Rules

```python
# Count recent transactions
from datetime import datetime, timedelta

cutoff = datetime.now() - timedelta(hours=1)

# Count events from this user in last hour
recent_count = count_user_events($user_id, since=cutoff)

if recent_count > 10:
    return True
```

### Multi-Factor Rules

```python
# Combine multiple signals
risk_score = 0

if $amount > 5000:
    risk_score += 2

if $is_international:
    risk_score += 1

if $account_age_days < 30:
    risk_score += 2

# Trigger if total risk is high
return risk_score >= 4
```

---


## Best Practices

### Performance

!!! tip "Avoid Heavy Queries"
    Keep rules fast - aim for under 100ms execution time. Cache frequently accessed data.

```python
# Bad: Queries database every time
def slow_rule(event):
    all_users = session.query(User).all()  # Loads entire table!
    blocked = [u.id for u in all_users if u.is_blocked]
    return event['user_id'] in blocked

# Good: Uses list notation
def fast_rule(event):
    return $user_id in @CACHED_BLOCKLIST
```

### Error Handling

```python
# Handle missing fields gracefully
try:
    amount = float($amount)
except (ValueError, TypeError):
    amount = 0

# Validate data types
if not isinstance($user_id, str):
    return False  # Invalid data
```

### Testing

Test rules before deployment:

```python
# Test cases
test_events = [
    {'amount': 15000, 'user_id': 'u1'},  # Should trigger
    {'amount': 500, 'user_id': 'u2'},    # Should not trigger
]

for test_event in test_events:
    result = evaluate_event(test_event)
    print(f"Event {test_event}: {result}")
```

---

## Advanced Techniques

### Time-Based Rules

```python
# Flag unusual transaction times
# Night transactions (2 AM - 5 AM)
if 2 <= $hour <= 5 and $amount > 1000:
    return True
```

### Pattern Matching

```python
import re

# Flag suspicious descriptions
suspicious_patterns = [
    r'test',
    r'fake',
    r'\b(wire|transfer)\b.*urgnet',  # Typos common in fraud
]

description = $description.lower()

for pattern in suspicious_patterns:
    if re.search(pattern, description):
        return True
```

### Statistical Rules

```python
# Flag outliers (Z-score > 3)
user_avg = get_user_avg_amount($user_id)
user_std = get_user_std_amount($user_id)

z_score = ($amount - user_avg) / user_std if user_std > 0 else 0

if abs(z_score) > 3:
    return True
```

---

## Rule Management

### Version Control

Rules are stored with version history:

1. Edit rule in web interface
2. Save creates new version
3. View history in **Rule Details → History**
4. Rollback to previous version if needed

### Testing Changes

Before deploying rule changes:

1. Use **Backtest** feature with historical data
2. Review results for false positives
3. Compare performance vs. current version
4. Deploy only if improvement is clear

---

## Examples

### Geographic Risk

```python
# High risk countries: always flag if > $1000
if $country in @HIGH_RISK_COUNTRIES and $amount > 1000:
    return True

# Medium risk: flag if > $5000
if $country in @MEDIUM_RISK_COUNTRIES and $amount > 5000:
    return True
```

### Merchant Category Risk

```python
if $merchant_category_code in @HIGH_RISK_MCCS:
    # Additional checks for high-risk merchants
    if not $card_present:
        return True  # Card-not-present in risky MCC
```

### First-Time User

```python
# New users with large first transaction
if $account_age_days < 7 and $amount > 2000:
    return True
```

---

## Debugging Rules

### Add Logging

```python
import logging

logger = logging.getLogger(__name__)

def my_rule(event):
    logger.info(f"Evaluating amount: {$amount}")

    if $amount > 10000:
        logger.warning(f"High amount detected: {$amount}")
        return True

    return False
```

### Use Test Data

```bash
# Generate test events
uv run ezrules generate-random-data --n-events 100

# Check outcomes
# View in web interface under Outcomes
```

---

## Next Steps

- **[Managing Outcomes](managing-outcomes.md)** - Link rules to actions
- **[Analyst Guide](analyst-guide.md)** - Comprehensive analyst workflows
- **[Labels and Lists](labels-and-lists.md)** - Work with user lists
