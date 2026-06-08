import unittest

from pycodex.core.guardian import (
    AUTO_REVIEW_DENIAL_WINDOW_SIZE,
    AUTO_REVIEW_DENIED_ACTION_APPROVAL_DEVELOPER_PREFIX,
    GUARDIAN_REVIEWER_NAME,
    GUARDIAN_REVIEW_TIMEOUT_SECONDS,
    MAX_CONSECUTIVE_GUARDIAN_DENIALS_PER_TURN,
    MAX_RECENT_AUTO_REVIEW_DENIALS_PER_TURN,
    GuardianRejectionCircuitBreaker,
    GuardianRejectionCircuitBreakerAction,
)


class GuardianRootTests(unittest.TestCase):
    def test_root_constants_match_guardian_mod_contract(self) -> None:
        # Rust source: codex-rs/core/src/guardian/mod.rs.
        self.assertEqual(GUARDIAN_REVIEW_TIMEOUT_SECONDS, 90)
        self.assertEqual(GUARDIAN_REVIEWER_NAME, "guardian")
        self.assertEqual(MAX_CONSECUTIVE_GUARDIAN_DENIALS_PER_TURN, 3)
        self.assertEqual(MAX_RECENT_AUTO_REVIEW_DENIALS_PER_TURN, 10)
        self.assertEqual(AUTO_REVIEW_DENIAL_WINDOW_SIZE, 50)
        self.assertIn("previously `Rejected`", AUTO_REVIEW_DENIED_ACTION_APPROVAL_DEVELOPER_PREFIX)

    def test_interrupts_after_three_consecutive_denials(self) -> None:
        # Rust test: guardian_rejection_circuit_breaker_interrupts_after_three_consecutive_denials.
        circuit_breaker = GuardianRejectionCircuitBreaker()

        self.assertEqual(circuit_breaker.record_denial("turn-1"), GuardianRejectionCircuitBreakerAction.continue_())
        self.assertEqual(circuit_breaker.record_denial("turn-1"), GuardianRejectionCircuitBreakerAction.continue_())
        self.assertEqual(
            circuit_breaker.record_denial("turn-1"),
            GuardianRejectionCircuitBreakerAction.interrupt_turn(
                consecutive_denials=3,
                recent_denials=3,
            ),
        )
        self.assertEqual(circuit_breaker.record_denial("turn-1"), GuardianRejectionCircuitBreakerAction.continue_())

    def test_non_denial_resets_consecutive_denials(self) -> None:
        # Rust test: guardian_rejection_circuit_breaker_resets_consecutive_denials_on_non_denial.
        circuit_breaker = GuardianRejectionCircuitBreaker()

        self.assertEqual(circuit_breaker.record_denial("turn-1"), GuardianRejectionCircuitBreakerAction.continue_())
        circuit_breaker.record_non_denial("turn-1")
        self.assertEqual(circuit_breaker.record_denial("turn-1"), GuardianRejectionCircuitBreakerAction.continue_())
        self.assertEqual(circuit_breaker.record_denial("turn-1"), GuardianRejectionCircuitBreakerAction.continue_())
        self.assertEqual(
            circuit_breaker.record_denial("turn-1"),
            GuardianRejectionCircuitBreakerAction.interrupt_turn(
                consecutive_denials=3,
                recent_denials=4,
            ),
        )

    def test_interrupts_after_ten_recent_denials(self) -> None:
        # Rust test: auto_review_rejection_circuit_breaker_interrupts_after_ten_recent_denials.
        circuit_breaker = GuardianRejectionCircuitBreaker()

        for _ in range(9):
            self.assertEqual(circuit_breaker.record_denial("turn-1"), GuardianRejectionCircuitBreakerAction.continue_())
            circuit_breaker.record_non_denial("turn-1")

        self.assertEqual(
            circuit_breaker.record_denial("turn-1"),
            GuardianRejectionCircuitBreakerAction.interrupt_turn(
                consecutive_denials=1,
                recent_denials=10,
            ),
        )

    def test_forgets_denials_outside_recent_review_window(self) -> None:
        # Rust test: auto_review_rejection_circuit_breaker_forgets_denials_outside_recent_review_window.
        circuit_breaker = GuardianRejectionCircuitBreaker()

        for _ in range(9):
            self.assertEqual(circuit_breaker.record_denial("turn-1"), GuardianRejectionCircuitBreakerAction.continue_())
            circuit_breaker.record_non_denial("turn-1")
        for _ in range(AUTO_REVIEW_DENIAL_WINDOW_SIZE - 18):
            circuit_breaker.record_non_denial("turn-1")

        self.assertEqual(circuit_breaker.record_denial("turn-1"), GuardianRejectionCircuitBreakerAction.continue_())

    def test_clear_turn_resets_turn_state(self) -> None:
        circuit_breaker = GuardianRejectionCircuitBreaker()

        circuit_breaker.record_denial("turn-1")
        circuit_breaker.record_denial("turn-1")
        circuit_breaker.clear_turn("turn-1")

        self.assertEqual(circuit_breaker.record_denial("turn-1"), GuardianRejectionCircuitBreakerAction.continue_())


if __name__ == "__main__":
    unittest.main()
