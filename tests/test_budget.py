import concurrent.futures
from pathlib import Path
import tempfile
import unittest
from lab.budget import BudgetExceeded, Ledger


class BudgetTests(unittest.TestCase):
    def test_concurrent_admission_and_restart_do_not_reset_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ledger.sqlite'
            ledger = Ledger(path, total_usd=1)
            token = ledger.register('run', max_requests=10, max_tokens=1000, wall_seconds=60)
            def reserve(_):
                try:
                    return Ledger(path, total_usd=100).reserve(token, max_tokens=100, worst_cost_usd=.3)[0]
                except BudgetExceeded:
                    return None
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                admitted = [r for r in pool.map(reserve, range(8)) if r]
            self.assertEqual(len(admitted), 3)
            ledger.settle(admitted[0], used_tokens=10, cost_usd=.01)
            ledger.reserve(token, max_tokens=100, worst_cost_usd=.3)
            with self.assertRaises(BudgetExceeded):
                ledger.reserve(token, max_tokens=100, worst_cost_usd=.3)
            with self.assertRaises(ValueError):
                ledger.settle(admitted[0], used_tokens=10, cost_usd=.01)

    def test_crashed_requests_retain_reservations_and_run_can_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp) / 'ledger.sqlite')
            token = ledger.register('run', max_requests=5, max_tokens=150, wall_seconds=60)
            ledger.reserve(token, max_tokens=100, worst_cost_usd=.01)
            with self.assertRaises(BudgetExceeded):
                ledger.reserve(token, max_tokens=100, worst_cost_usd=.01)
            ledger.close('run')
            with self.assertRaises(BudgetExceeded):
                ledger.reserve(token, max_tokens=1, worst_cost_usd=.01)

    def test_expiry_and_wrong_token_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp) / 'ledger.sqlite')
            token = ledger.register('run', max_requests=5, max_tokens=150, wall_seconds=60)
            with ledger.transaction() as db:
                db.execute('UPDATE runs SET deadline=0')
            for candidate in (token, 'invented'):
                with self.assertRaises(BudgetExceeded):
                    ledger.reserve(candidate, max_tokens=1, worst_cost_usd=.01)
