import argparse
import random
from random import randint
from core.rule import Rule
from core.rule_engine import RuleEngine
from core.rule_updater import RuleEngineConfigProducer, FSRuleManager
import json
from pathlib import Path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--num-params", help="Number of attributes input facts have", default=100
    )
    parser.add_argument("--num-rules", help="Number of rules to test", default=200)
    parser.add_argument("--num-facts", help="Number of facts to test", default=1000)
    args = parser.parse_args()
    num_params = args.num_params
    num_rules = args.num_rules
    num_facts = args.num_facts
    output_path = Path("/Users/sofeikov")

    all_facts = []
    for f in range(num_facts):
        new_fact = {f"param_{i}": random.randint(1, 5) for i in range(num_params + 1)}
        all_facts.append(new_fact)
    with open(output_path / "facts.json", "w+") as f:
        json.dump(all_facts, f)
    print(all_facts)

    rules = []
    manager = FSRuleManager(output_path / "rules_load_test")
    for rct in range(num_rules):
        rule_code = []
        num_checks = random.randint(1, num_params)
        checks = []
        for i in range(num_checks):
            checks.append(f"$param_{randint(0, num_params)} == {randint(1, 5)}")
        checks = "if " + " and ".join(checks) + ":"
        rule_code.append(checks)
        rule_code.append("\treturn 'HOLD'")
        rule_code.append("return 'RELEASE'")
        rule_code = "\n".join(rule_code)
        rule = Rule(rid=f"rule_{rct}", logic=rule_code)
        rules.append(rule)
        manager.save_rule(rule)
        print(rule)
    # rule_engine = RuleEngine(rules=rules)
    RuleEngineConfigProducer.to_yaml(output_path / "rules.yaml", manager)
    import time

    tic = time.time()
    re = RuleEngine(rules=rules)
    for f in all_facts:
        re(f)

    toc = time.time()
    print(f"Time taken: {toc - tic} for {num_rules} rules, {num_facts} facts")
