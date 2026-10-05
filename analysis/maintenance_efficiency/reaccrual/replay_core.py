"""Pure logic of the re-accrual replay runner: scheduling, budget admission, step verdicts and confirmatory statistics."""
import hashlib
import json
import math
from collections import Counter
from fractions import Fraction

from scipy import stats

BYTES_PER_TOKEN = 3.5
RESERVATION_MARGIN = 1.1
FRAMING_TOKENS = 512


def decode_source(data):
    """Bouw sources are UTF-8 or Windows-1252; states are written back as UTF-8, which the compiler reads identically."""
    try:
        return data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return data.decode('cp1252')


def branch_order(seed, target_id, branches):
    return sorted(branches, key=lambda b: hashlib.sha256(f'{seed}|{target_id}|{b[0]}{b[1]}'.encode()).hexdigest())


def reservation(messages):
    size = len(json.dumps(messages, ensure_ascii=False).encode('utf-8'))
    return math.ceil(size / BYTES_PER_TOKEN * RESERVATION_MARGIN) + FRAMING_TOKENS


def may_call(spent, reserve, max_output, allocation):
    return spent + reserve + max_output <= allocation


def step_verdict(build_ok, api_missing, reference, fail_to_pass, candidate, within_allocation):
    """Return (completed, failure_stage). Required tests are those passing in the developers' post-commit state."""
    if not build_ok:
        return False, 'build'
    if api_missing:
        return False, 'api'
    required = {t for t, o in reference.items() if o == 'Passed'}
    failing = {t for t in required if candidate.get(t) != 'Passed'}
    if failing & set(fail_to_pass):
        return False, 'fail_to_pass'
    if failing:
        return False, 'regression'
    if not within_allocation:
        return False, 'allocation'
    return True, None


def completed_prefix(verdicts):
    count = 0
    for completed in verdicts:
        if not completed:
            break
        count += 1
    return count


def accrual(series, j):
    """Per-change accrual between state 0 and state j of one branch; None when no step was completed."""
    return None if j == 0 else (series[j] - series[0]) / j


def sign_flip_greater(differences):
    """Exact one-sided sign-flip p-value for a positive mean difference."""
    fractions = [Fraction(d).limit_denominator(10 ** 6) for d in differences]
    scale = math.lcm(*(f.denominator for f in fractions)) if fractions else 1
    weights = [int(f * scale) for f in fractions]
    distribution = Counter({0: 1})
    for w in weights:
        nxt = Counter()
        for value, n in distribution.items():
            nxt[value + w] += n
            nxt[value - w] += n
        distribution = nxt
    observed = sum(weights)
    return sum(n for v, n in distribution.items() if v >= observed) / 2 ** len(weights)


def t_interval(differences, confidence):
    n = len(differences)
    mean = sum(differences) / n
    sd = math.sqrt(sum((d - mean) ** 2 for d in differences) / (n - 1))
    half = stats.t.ppf(1 - (1 - confidence) / 2, n - 1) * sd / math.sqrt(n)
    return mean - half, mean + half


def holm(pvalues):
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted, running = [0.0] * m, 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def kaplan_meier_recurrence(observations, horizon):
    """observations: (time, recurred) per branch; returns cumulative recurrence by step 1..horizon."""
    survival, curve = 1.0, {}
    for t in range(1, horizon + 1):
        at_risk = sum(1 for time, _ in observations if time >= t)
        events = sum(1 for time, recurred in observations if time == t and recurred)
        if at_risk:
            survival *= 1 - events / at_risk
        curve[t] = 1 - survival
    return curve


def clopper_pearson(k, n, confidence=0.95):
    alpha = 1 - confidence
    low = 0.0 if k == 0 else stats.beta.ppf(alpha / 2, k, n - k + 1)
    high = 1.0 if k == n else stats.beta.ppf(1 - alpha / 2, k + 1, n - k)
    return low, high
