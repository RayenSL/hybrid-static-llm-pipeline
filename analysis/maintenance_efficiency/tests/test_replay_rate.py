import io
import sys
import unittest
import urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import replay_rate as rate


class PacingTests(unittest.TestCase):
    def test_no_wait_under_limit(self):
        self.assertEqual(rate.wait_needed([], now=0, amount=50_000, limit=236_000), 0)
        self.assertEqual(rate.wait_needed([(0, 100_000)], now=10, amount=50_000, limit=236_000), 0)

    def test_wait_until_window_frees(self):
        self.assertEqual(rate.wait_needed([(0, 200_000)], now=10, amount=50_000, limit=236_000), 50)

    def test_old_reservations_leave_the_window(self):
        self.assertEqual(rate.wait_needed([(0, 200_000)], now=61, amount=50_000, limit=236_000), 0)

    def test_single_request_above_limit_is_refused(self):
        with self.assertRaises(ValueError):
            rate.wait_needed([], now=0, amount=300_000, limit=236_000)


class RetryTests(unittest.TestCase):
    def http_error(self, code, retry_after=None):
        headers = {'Retry-After': str(retry_after)} if retry_after is not None else {}
        return urllib.error.HTTPError('https://example.invalid', code, 'error', headers, io.BytesIO(b'{}'))

    def test_429_releases_reservation_waits_and_retries(self):
        events, sleeps = [], []
        calls = iter([self.http_error(429, retry_after=7), 'ok'])

        def call():
            item = next(calls)
            if isinstance(item, Exception):
                raise item
            return item
        result = rate.with_rate_limit_retry(call, release=lambda: events.append('released'), sleep=sleeps.append, attempts=3)
        self.assertEqual(result, 'ok')
        self.assertEqual(events, ['released'])
        self.assertEqual(sleeps, [7])

    def test_other_http_errors_are_not_retried(self):
        def call():
            raise self.http_error(500)
        with self.assertRaises(urllib.error.HTTPError):
            rate.with_rate_limit_retry(call, release=lambda: None, sleep=lambda s: None, attempts=3)

    def test_retries_are_bounded(self):
        def call():
            raise self.http_error(429)
        with self.assertRaises(urllib.error.HTTPError):
            rate.with_rate_limit_retry(call, release=lambda: None, sleep=lambda s: None, attempts=2)


if __name__ == '__main__':
    unittest.main()
