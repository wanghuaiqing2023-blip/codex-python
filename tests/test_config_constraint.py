import unittest

from pycodex.config import Constrained, ConstraintError, RequirementSource


def invalid_value(candidate: str, allowed: str) -> ConstraintError:
    return ConstraintError.invalid_value(
        field_name="<unknown>",
        candidate=candidate,
        allowed=allowed,
        requirement_source=RequirementSource.unknown(),
    )


class ConfigConstraintTests(unittest.TestCase):
    def test_constrained_allow_any_accepts_any_value(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/constraint.rs
        # Rust test: constrained_allow_any_accepts_any_value
        constrained = Constrained.allow_any(5)

        constrained.set(-10)

        self.assertEqual(constrained.value(), -10)

    def test_constrained_allow_any_default_uses_default_value(self) -> None:
        # Rust test: constrained_allow_any_default_uses_default_value
        constrained = Constrained.allow_any_from_default(0)

        self.assertEqual(constrained.value(), 0)

    def test_constrained_allow_only_rejects_different_values(self) -> None:
        # Rust test: constrained_allow_only_rejects_different_values
        constrained = Constrained.allow_only(5)

        constrained.set(5)
        with self.assertRaises(ConstraintError) as caught:
            constrained.set(6)

        self.assertEqual(caught.exception, invalid_value("6", "[5]"))
        self.assertEqual(constrained.value(), 5)

    def test_constrained_normalizer_applies_on_init_and_set(self) -> None:
        # Rust test: constrained_normalizer_applies_on_init_and_set
        constrained = Constrained.normalized(-1, lambda value: max(value, 0))

        self.assertEqual(constrained.value(), 0)
        constrained.set(-5)
        self.assertEqual(constrained.value(), 0)
        constrained.set(10)
        self.assertEqual(constrained.value(), 10)

    def test_constrained_can_set_does_not_apply_normalizer(self) -> None:
        # Rust source: Constrained::can_set validates the candidate directly.
        constrained = Constrained.normalized(-1, lambda value: max(value, 0))

        constrained.can_set(-5)

        self.assertEqual(constrained.value(), 0)

    def test_constrained_add_validator_composes_with_existing_validator(self) -> None:
        # Rust test: constrained_add_validator_composes_with_existing_validator
        constrained = Constrained.new(5, _positive_validator)

        constrained.add_validator(_at_most_ten_validator)

        constrained.can_set(7)
        with self.assertRaises(ConstraintError) as high:
            constrained.can_set(11)
        self.assertEqual(high.exception, ConstraintError.empty_field("value"))
        with self.assertRaises(ConstraintError) as low:
            constrained.can_set(-1)
        self.assertEqual(low.exception, ConstraintError.empty_field("value"))

    def test_constrained_new_rejects_invalid_initial_value(self) -> None:
        # Rust test: constrained_new_rejects_invalid_initial_value
        with self.assertRaises(ConstraintError) as caught:
            Constrained.new(0, _strict_positive_validator)

        self.assertEqual(caught.exception, invalid_value("0", "positive values"))

    def test_constrained_set_rejects_invalid_value_and_leaves_previous(self) -> None:
        # Rust test: constrained_set_rejects_invalid_value_and_leaves_previous
        constrained = Constrained.new(1, _strict_positive_validator)

        with self.assertRaises(ConstraintError) as caught:
            constrained.set(-5)

        self.assertEqual(caught.exception, invalid_value("-5", "positive values"))
        self.assertEqual(constrained.value(), 1)

    def test_constrained_can_set_allows_probe_without_setting(self) -> None:
        # Rust test: constrained_can_set_allows_probe_without_setting
        constrained = Constrained.new(1, _strict_positive_validator)

        constrained.can_set(2)
        with self.assertRaises(ConstraintError) as caught:
            constrained.can_set(-1)

        self.assertEqual(caught.exception, invalid_value("-1", "positive values"))
        self.assertEqual(constrained.value(), 1)

    def test_constraint_error_messages_match_rust_display(self) -> None:
        # Rust source: ConstraintError Display impl via thiserror messages.
        self.assertEqual(
            str(invalid_value("Never", "[OnRequest]")),
            "invalid value for `<unknown>`: `Never` is not in the allowed set [OnRequest] (set by <unspecified>)",
        )
        self.assertEqual(str(ConstraintError.empty_field("profile")), "field `profile` cannot be empty")
        self.assertEqual(
            str(
                ConstraintError.exec_policy_parse(
                    requirement_source=RequirementSource.cloud_requirements(),
                    reason="bad prefix_rule",
                )
            ),
            "invalid rules in requirements (set by cloud requirements): bad prefix_rule",
        )


def _positive_validator(value: int) -> None:
    if value < 0:
        raise ConstraintError.empty_field("value")


def _at_most_ten_validator(value: int) -> None:
    if value > 10:
        raise ConstraintError.empty_field("value")


def _strict_positive_validator(value: int) -> None:
    if value <= 0:
        raise invalid_value(str(value), "positive values")


if __name__ == "__main__":
    unittest.main()
