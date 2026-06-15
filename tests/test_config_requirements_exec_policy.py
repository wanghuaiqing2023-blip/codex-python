import unittest

from pycodex.config import (
    RequirementsExecPolicyDecisionToml,
    RequirementsExecPolicyParseError,
    RequirementsExecPolicyPatternTokenToml,
    RequirementsExecPolicyPrefixRuleToml,
    RequirementsExecPolicyToml,
)
from pycodex.execpolicy import Decision


class ConfigRequirementsExecPolicyTests(unittest.TestCase):
    def test_to_requirements_policy_builds_prompt_and_forbidden_prefix_rules(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/requirements_exec_policy.rs
        # Behavior anchor: RequirementsExecPolicyToml::to_policy converts TOML
        # prefix_rules into internal execpolicy prefix rules.
        toml = RequirementsExecPolicyToml(
            prefix_rules=(
                RequirementsExecPolicyPrefixRuleToml(
                    pattern=(
                        RequirementsExecPolicyPatternTokenToml(token="git"),
                        RequirementsExecPolicyPatternTokenToml(any_of=("push", "fetch")),
                    ),
                    decision=RequirementsExecPolicyDecisionToml.PROMPT,
                    justification="review remote access",
                ),
                RequirementsExecPolicyPrefixRuleToml(
                    pattern=(RequirementsExecPolicyPatternTokenToml(token="rm"),),
                    decision=RequirementsExecPolicyDecisionToml.FORBIDDEN,
                ),
            )
        )

        policy = toml.to_requirements_policy()

        self.assertEqual(len(policy.prefix_rules), 2)
        self.assertEqual(policy.prefix_rules[0].pattern, ("git", ("push", "fetch")))
        self.assertEqual(policy.prefix_rules[0].decision, Decision.PROMPT)
        self.assertEqual(policy.prefix_rules[0].justification, "review remote access")
        self.assertEqual(policy.prefix_rules[1].pattern, ("rm",))
        self.assertEqual(policy.prefix_rules[1].decision, Decision.FORBIDDEN)
        self.assertEqual(toml.to_policy(), {"prefix_rules": policy.prefix_rules})

    def test_first_token_alternatives_expand_into_program_rules(self) -> None:
        # Rust source: to_policy inserts one PrefixRule for each first-token alternative.
        toml = RequirementsExecPolicyToml(
            prefix_rules=(
                RequirementsExecPolicyPrefixRuleToml(
                    pattern=(
                        RequirementsExecPolicyPatternTokenToml(any_of=("python", "python3")),
                        RequirementsExecPolicyPatternTokenToml(token="-m"),
                    ),
                    decision=RequirementsExecPolicyDecisionToml.PROMPT,
                ),
            )
        )

        rules = toml.to_requirements_policy().prefix_rules

        self.assertEqual([rule.pattern for rule in rules], [("python", "-m"), ("python3", "-m")])

    def test_requirements_policy_equality_uses_policy_fingerprint(self) -> None:
        # Rust source: RequirementsExecPolicy PartialEq compares sorted policy fingerprints.
        first = RequirementsExecPolicyToml(
            prefix_rules=(
                _rule("git", "prompt"),
                _rule("rm", "forbidden"),
            )
        ).to_requirements_policy()
        second = RequirementsExecPolicyToml(
            prefix_rules=(
                _rule("rm", "forbidden"),
                _rule("git", "prompt"),
            )
        ).to_requirements_policy()

        self.assertEqual(first, second)

    def test_empty_prefix_rules_is_rejected(self) -> None:
        # Rust error: EmptyPrefixRules.
        with self.assertRaises(RequirementsExecPolicyParseError) as caught:
            RequirementsExecPolicyToml(prefix_rules=()).to_policy()

        self.assertEqual(str(caught.exception), "rules prefix_rules cannot be empty")

    def test_empty_pattern_is_rejected(self) -> None:
        # Rust error: EmptyPattern.
        toml = RequirementsExecPolicyToml(
            prefix_rules=(
                RequirementsExecPolicyPrefixRuleToml(
                    pattern=(),
                    decision=RequirementsExecPolicyDecisionToml.PROMPT,
                ),
            )
        )

        with self.assertRaises(RequirementsExecPolicyParseError) as caught:
            toml.to_policy()

        self.assertEqual(str(caught.exception), "rules prefix_rule at index 0 has an empty pattern")

    def test_empty_justification_is_rejected(self) -> None:
        # Rust error: EmptyJustification.
        toml = RequirementsExecPolicyToml(
            prefix_rules=(
                RequirementsExecPolicyPrefixRuleToml(
                    pattern=(RequirementsExecPolicyPatternTokenToml(token="pwd"),),
                    decision=RequirementsExecPolicyDecisionToml.PROMPT,
                    justification=" \n\t",
                ),
            )
        )

        with self.assertRaises(RequirementsExecPolicyParseError) as caught:
            toml.to_policy()

        self.assertEqual(str(caught.exception), "rules prefix_rule at index 0 has an empty justification")

    def test_missing_decision_and_allow_decision_are_rejected(self) -> None:
        # Rust errors: MissingDecision and AllowDecisionNotAllowed.
        missing = RequirementsExecPolicyToml(
            prefix_rules=(RequirementsExecPolicyPrefixRuleToml(pattern=(RequirementsExecPolicyPatternTokenToml(token="pwd"),)),)
        )
        allowed = RequirementsExecPolicyToml(
            prefix_rules=(
                RequirementsExecPolicyPrefixRuleToml(
                    pattern=(RequirementsExecPolicyPatternTokenToml(token="pwd"),),
                    decision=RequirementsExecPolicyDecisionToml.ALLOW,
                ),
            )
        )

        with self.assertRaises(RequirementsExecPolicyParseError) as missing_err:
            missing.to_policy()
        self.assertEqual(str(missing_err.exception), "rules prefix_rule at index 0 is missing a decision")

        with self.assertRaises(RequirementsExecPolicyParseError) as allow_err:
            allowed.to_policy()
        self.assertIn("decision 'allow'", str(allow_err.exception))
        self.assertIn("use 'prompt' or 'forbidden'", str(allow_err.exception))

    def test_invalid_pattern_tokens_are_rejected(self) -> None:
        # Rust errors: InvalidPatternToken for every token shape branch.
        cases = (
            (RequirementsExecPolicyPatternTokenToml(token=" "), "token cannot be empty"),
            (RequirementsExecPolicyPatternTokenToml(any_of=()), "any_of cannot be empty"),
            (RequirementsExecPolicyPatternTokenToml(any_of=("git", "")), "any_of cannot include empty tokens"),
            (RequirementsExecPolicyPatternTokenToml(token="git", any_of=("git",)), "set either token or any_of, not both"),
            (RequirementsExecPolicyPatternTokenToml(), "set either token or any_of"),
        )
        for token, reason in cases:
            with self.subTest(reason=reason):
                toml = RequirementsExecPolicyToml(
                    prefix_rules=(
                        RequirementsExecPolicyPrefixRuleToml(
                            pattern=(token,),
                            decision=RequirementsExecPolicyDecisionToml.PROMPT,
                        ),
                    )
                )
                with self.assertRaises(RequirementsExecPolicyParseError) as caught:
                    toml.to_policy()
                self.assertEqual(
                    str(caught.exception),
                    f"rules prefix_rule at index 0 has an invalid pattern token at index 0: {reason}",
                )

    def test_from_mapping_accepts_toml_like_dicts(self) -> None:
        # Rust serde shape: prefix_rules -> pattern token/any_of tables.
        toml = RequirementsExecPolicyToml.from_mapping(
            {
                "prefix_rules": [
                    {
                        "pattern": [{"token": "cargo"}, {"any_of": ["test", "build"]}],
                        "decision": "prompt",
                        "justification": "build commands",
                    }
                ]
            }
        )

        rule = toml.to_requirements_policy().prefix_rules[0]

        self.assertEqual(rule.pattern, ("cargo", ("test", "build")))
        self.assertEqual(rule.decision, Decision.PROMPT)
        self.assertEqual(rule.justification, "build commands")


def _rule(program: str, decision: str) -> RequirementsExecPolicyPrefixRuleToml:
    return RequirementsExecPolicyPrefixRuleToml(
        pattern=(RequirementsExecPolicyPatternTokenToml(token=program),),
        decision=RequirementsExecPolicyDecisionToml(decision),
    )


if __name__ == "__main__":
    unittest.main()
