"""Example evaluation workflow for the Policy-as-Code engine.

This file demonstrates how to prepare a context and run the engine. In a real
deployment policies and rules are stored in the DB and managed by operators.

This script is illustrative and is not intended to be executed as-is in this
repository (it requires migrations and DB objects). Use it as an example for
audit documentation.
"""
from policy.services import RuleEngine
from policy.models import Policy


def example_evaluation(policy_name: str, context: dict, user=None):
    """Lookup a policy by name and evaluate against the given context.

    Returns a fully explainable result suitable for audit.
    """
    policy = Policy.objects.get(name=policy_name)
    engine = RuleEngine()
    result = engine.evaluate_policy(policy, context, user=user)
    # result contains detailed rule evaluations and any violations recorded
    return result


if __name__ == '__main__':
    # Example context: a user upload event. Values are simple primitives.
    ctx = {
        'request': {'ip': '203.0.113.5', 'user_agent': 'curl/7.68.0'},
        'file': {'name': 'secrets.txt', 'size': 4200000},
        'user': {'username': 'jdoe', 'role': 'soldier'},
        # historical events and other metrics can be included for thresholds
        'history': [],
    }
    # Usage (requires DB objects to exist):
    # print(example_evaluation('Data Exfil Prevention', ctx, user=None))
    print('This is an example usage. See docstring for details.')
