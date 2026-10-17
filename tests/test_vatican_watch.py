import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import vatican_watch as vw  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


class Dates(unittest.TestCase):
    def test_parse_date_formats(self):
        for text in ("2026-10-17", "17/10/2026", "17.10.2026"):
            self.assertEqual(vw.parse_date(text), date(2026, 10, 17))

    def test_parse_date_rejects_garbage(self):
        with self.assertRaises(Exception):
            vw.parse_date("next friday")

    def test_rome_midnight_handles_dst(self):
        self.assertEqual(vw.rome_midnight_ms(date(2026, 10, 17)), 1792188000000)  # CEST, UTC+2
        self.assertEqual(vw.rome_midnight_ms(date(2026, 12, 2)), 1796166000000)   # CET, UTC+1


class Links(unittest.TestCase):
    def test_tagged_ticket_goes_to_top(self):
        self.assertEqual(
            vw.booking_link(date(2026, 10, 17), 4, "Vatican Museums - Admission Ticket"),
            "https://tickets.museivaticani.va/home/fromtag/4/1792188000000/MV-Biglietti/1?lang=en")

    def test_other_ticket_opens_list(self):
        self.assertEqual(
            vw.booking_link(date(2026, 10, 17), 2, "Guided Tours for Individuals - Art and Faith"),
            "https://tickets.museivaticani.va/home/visit/2/1792188000000/1/1?lang=en")


class Matching(unittest.TestCase):
    def test_substring_case_insensitive(self):
        self.assertTrue(vw.matches("Vatican Museums - Admission Ticket", ["admission"]))
        self.assertFalse(vw.matches("Vatican Gardens - Guided Tour", ["admission"]))

    def test_star_matches_everything(self):
        self.assertTrue(vw.matches("anything", ["*"]))


class SameDayPage(unittest.TestCase):
    def test_available(self):
        state, times, buy = vw.parse_same_day((FIXTURES / "same_day_available.html").read_text())
        self.assertEqual(state, "available")
        self.assertEqual(times, ["08:00"])
        self.assertEqual(buy, "https://tickets.museivaticani.va/home/visit/4/1792015200000/1?lang=en")

    def test_sold_out(self):
        state, times, buy = vw.parse_same_day((FIXTURES / "same_day_none.html").read_text())
        self.assertEqual((state, times, buy), ("none", [], None))

    def test_unknown_layout(self):
        state, _, _ = vw.parse_same_day("<html><body>maintenance</body></html>")
        self.assertEqual(state, "unknown")


class AlertDedup(unittest.TestCase):
    def test_sequence(self):
        alerted = {}
        key = "2026-10-17|Admission"
        self.assertTrue(vw.needs_alert(alerted, key, ["09:30", "15:30"]))   # new opening
        self.assertFalse(vw.needs_alert(alerted, key, ["15:30", "09:30"]))  # same times again
        self.assertFalse(vw.needs_alert(alerted, key, ["15:30"]))           # one got booked
        self.assertTrue(vw.needs_alert(alerted, key, ["15:30", "16:00"]))   # a new time showed up
        self.assertFalse(vw.needs_alert(alerted, key, []))                  # all gone
        self.assertNotIn(key, alerted)
        self.assertTrue(vw.needs_alert(alerted, key, ["15:30"]))            # freed up again


class Args(unittest.TestCase):
    def test_defaults(self):
        args = vw.parse_args(["--date", "2026-10-17"])
        self.assertEqual(args.tickets, vw.DEFAULT_TICKETS)
        self.assertEqual(args.visitors, 2)

    def test_interval_minimum(self):
        args = vw.parse_args(["--date", "2026-10-17", "--interval", "1"])
        self.assertEqual(args.interval, vw.MIN_INTERVAL)


if __name__ == "__main__":
    unittest.main()
