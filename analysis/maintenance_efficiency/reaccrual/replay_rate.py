"""Client-side pacing under the deployment's tokens-per-minute limit, and safe handling of HTTP 429 rejections."""
import urllib.error

WINDOW_SECONDS = 60


def wait_needed(history, now, amount, limit):
    """Seconds to wait before reserving amount, given (time, tokens) reservations in the sliding window."""
    if amount > limit:
        raise ValueError(f'A single request of {amount} tokens exceeds the {limit} tokens-per-minute limit')
    recent = sorted((t, n) for t, n in history if t > now - WINDOW_SECONDS)
    used = sum(n for _, n in recent)
    if used + amount <= limit:
        return 0
    for t, n in recent:
        used -= n
        if used + amount <= limit:
            return t + WINDOW_SECONDS - now
    return WINDOW_SECONDS


def with_rate_limit_retry(call, release, sleep, attempts):
    """Retry only HTTP 429: the provider refused the request unprocessed, so its reservation is released before waiting."""
    for attempt in range(attempts):
        try:
            return call()
        except urllib.error.HTTPError as error:
            if error.code != 429:
                raise
            release()
            if attempt == attempts - 1:
                raise
            retry_after = error.headers.get('Retry-After') if error.headers else None
            sleep(int(retry_after) if retry_after and retry_after.isdigit() else WINDOW_SECONDS)
