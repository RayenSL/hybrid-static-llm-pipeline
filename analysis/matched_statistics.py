"""Matched binary-outcome tests shared by the final context analysis."""
import math


def regularized_gamma_q(a: float, x: float) -> float:
    """Numerical Recipes regularized upper incomplete gamma Q(a, x)."""
    if x < 0 or a <= 0:
        raise ValueError("invalid gamma arguments")
    if x == 0:
        return 1.0
    eps = 3e-14
    tiny = 1e-300
    max_iter = 10000
    log_term = -x + a * math.log(x) - math.lgamma(a)
    if x < a + 1:
        ap = a
        total = 1.0 / a
        delta = total
        for _ in range(max_iter):
            ap += 1
            delta *= x / ap
            total += delta
            if abs(delta) < abs(total) * eps:
                return max(0.0, min(1.0, 1.0 - total * math.exp(log_term)))
        raise RuntimeError("gamma series did not converge")
    b = x + 1 - a
    c = 1 / tiny
    d = 1 / b
    h = d
    for i in range(1, max_iter + 1):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < eps:
            return max(0.0, min(1.0, math.exp(log_term) * h))
    raise RuntimeError("gamma continued fraction did not converge")

def cochran_q(matrix: list[list[int]]) -> tuple[float, int, float]:
    n = len(matrix)
    k = len(matrix[0])
    if any(len(row) != k for row in matrix):
        raise ValueError("ragged matched matrix")
    column_sums = [sum(matrix[i][j] for i in range(n)) for j in range(k)]
    row_sums = [sum(row) for row in matrix]
    total = sum(column_sums)
    denominator = k * total - sum(value * value for value in row_sums)
    if denominator == 0:
        return 0.0, k - 1, 1.0
    statistic = (k - 1) * (k * sum(value * value for value in column_sums) - total * total)
    statistic /= denominator
    return statistic, k - 1, regularized_gamma_q((k - 1) / 2, statistic / 2)

def exact_mcnemar(left: list[int], right: list[int]) -> tuple[int, int, float]:
    left_only = sum(a == 1 and b == 0 for a, b in zip(left, right))
    right_only = sum(a == 0 and b == 1 for a, b in zip(left, right))
    discordant = left_only + right_only
    if discordant == 0:
        return left_only, right_only, 1.0
    low = min(left_only, right_only)
    tail = sum(math.comb(discordant, value) for value in range(low + 1)) / (2**discordant)
    return left_only, right_only, min(1.0, 2 * tail)

def holm_adjust(p_values: list[float]) -> list[float]:
    indexed = sorted(enumerate(p_values), key=lambda pair: pair[1])
    adjusted = [0.0] * len(p_values)
    running = 0.0
    m = len(p_values)
    for rank, (original_index, value) in enumerate(indexed):
        running = max(running, min(1.0, (m - rank) * value))
        adjusted[original_index] = running
    return adjusted
