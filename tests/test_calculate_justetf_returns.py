import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import calculate_justetf_returns as app


class CalculateReturnsTests(unittest.TestCase):
    def test_extract_isin_accepts_url_and_normalizes_case(self):
        self.assertEqual(
            app.extract_isin("https://justetf.com/profile?isin=ie00bl25jp72"),
            "IE00BL25JP72",
        )

    def test_monthly_returns_uses_last_price_per_month(self):
        prices = pd.DataFrame(
            {
                "ticker": ["TEST", "TEST", "TEST"],
                "date": pd.to_datetime(["2025-01-30", "2025-01-31", "2025-02-28"]),
                "price": [99.0, 100.0, 110.0],
            }
        )
        result = app.monthly_returns(app.month_end_prices(prices))
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result.iloc[0]["yield_decimal"], 0.10)

    def test_invalid_and_duplicate_instruments_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instruments.csv"
            path.write_text("ticker,isin_or_url\nTEST,IE00BL25JP72\ntest,IE00B8FHGS14\n")
            with self.assertRaisesRegex(ValueError, "duplicate ticker"):
                app.read_instruments(path)

    def test_weight_total_warning_and_contribution(self):
        returns = pd.DataFrame(
            {
                "ticker": ["TEST"],
                "month": pd.PeriodIndex(["2025-02"], freq="M"),
                "yield_decimal": [0.10],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weights.csv"
            path.write_text("date,ticker,weight\n2025-02-01,TEST,50%\n")
            output = io.StringIO()
            with contextlib.redirect_stderr(output):
                result = app.attach_weights(returns, path)
            self.assertIn("total 50,00% instead of 100%", output.getvalue())
            self.assertEqual(result.iloc[0]["portfolio_monthly_yield"], "5,00%")

    def test_download_retries_transient_failure(self):
        chart = pd.DataFrame(
            {"date": pd.to_datetime(["2025-01-31"]), "quote": [100.0]}
        ).set_index("date")
        instrument = app.Instrument("TEST", "IE00BL25JP72")
        with patch.object(
            app.justetf_scraping,
            "load_chart",
            side_effect=[ConnectionError("temporary"), chart],
        ), patch.object(app.time, "sleep") as sleep:
            result = app.load_chart_for_instrument(instrument, retries=2)
        self.assertEqual(result.iloc[0]["price"], 100.0)
        sleep.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
