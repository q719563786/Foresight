import unittest

from yuanjian_app.rules import create_candidate


class RuleTests(unittest.TestCase):
    def test_medical_payment_event_creates_health_and_cashflow_candidate(self):
        candidate = create_candidate("医院最终自付9500元，8月8日结算", "2026-08-08")

        self.assertIn("health", candidate["domains"])
        self.assertIn("cashflow", candidate["domains"])
        self.assertTrue(candidate["requires_human_confirmation"])
        self.assertEqual(candidate["amounts"], [9500.0])

    def test_event_without_future_window_stays_a_signal(self):
        candidate = create_candidate("客户今天聊过一次", "2026-08-08")

        self.assertFalse(candidate["can_register_forecast"])


if __name__ == "__main__":
    unittest.main()
