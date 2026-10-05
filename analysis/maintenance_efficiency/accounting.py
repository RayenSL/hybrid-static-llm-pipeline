"""Strict token/cost accounting for paired maintenance runs; standard library only."""
from decimal import Decimal, ROUND_CEILING


def count(value, name, nullable=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f'{name} must be a nonnegative integer' + (' or null' if nullable else ''))
    return value


def validate_call(call):
    for field in ['call_id', 'model', 'outcome']:
        if not isinstance(call.get(field),str) or not call[field]:
            raise ValueError(f'Missing {field}')
    if call['outcome'] not in ['completed','failed','cancelled']:
        raise ValueError('Unknown call outcome')
    inp=count(call.get('input_tokens'),'input_tokens',True)
    out=count(call.get('output_tokens'),'output_tokens',True)
    cache=count(call.get('cached_input_tokens'),'cached_input_tokens',True)
    reasoning=count(call.get('reasoning_output_tokens'),'reasoning_output_tokens',True)
    if cache is not None and (inp is None or cache>inp):
        raise ValueError('Cached input must be a subset of total input')
    if reasoning is not None and (out is None or reasoning>out):
        raise ValueError('Reasoning output must be a subset of total output')
    return inp,out,cache,reasoning


def price_call(call, prices):
    inp,out,cache,_=validate_call(call)
    if prices is None or inp is None or out is None:
        return None
    if prices.get('model')!=call['model']:
        raise ValueError('Price model differs from recorded model')
    rates=[]
    for key in ['input_per_million','cached_input_per_million','output_per_million']:
        value=Decimal(str(prices[key]))
        if not value.is_finite() or value<0:raise ValueError('Rates must be finite and nonnegative')
        rates.append(value)
    regular,cached,output=rates
    if cache is None and regular!=cached:
        return None
    # Missing cache split is harmless only when cached and regular rates are equal.
    cache=cache or 0
    return (Decimal(inp-cache)*regular+Decimal(cache)*cached+Decimal(out)*output)/Decimal(1_000_000)


def summarize_run(run, prices=None):
    budget=count(run.get('token_budget'),'token_budget')
    if not budget:raise ValueError('Budget must be positive')
    gate_fields=['acceptance_passed','regression_passed','edit_scope_passed','integrity_passed']
    for field in gate_fields:
        if run.get(field) is not None and not isinstance(run[field],bool):raise ValueError(f'{field} must be bool or null')
    calls=run['calls'];ids=[c['call_id'] for c in calls]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate call_id within run')
    observed=[validate_call(c) for c in calls]
    complete=all(i is not None and o is not None for i,o,_,_ in observed)
    # Partial usage is reported as a lower bound, never silently used as the total.
    lower_bound=sum((i or 0)+(o or 0) for i,o,_,_ in observed)
    total=lower_bound if complete else None
    priced=[price_call(c,prices) for c in calls]
    amount=sum(priced,Decimal(0)) if prices is not None and all(p is not None for p in priced) else None
    gates=all(run.get(field) is True for field in gate_fields)
    known_failure=any(run.get(field) is False for field in gate_fields) or lower_bound>budget
    outcome=False if known_failure else (True if gates and complete else None)
    return dict(call_count=len(calls),failed_calls=sum(c['outcome']!='completed' for c in calls),
                usage_complete=complete,total_tokens=total,observed_token_lower_bound=lower_bound,
                input_tokens=sum(i for i,_,_,_ in observed) if all(i is not None for i,_,_,_ in observed) else None,
                output_tokens=sum(o for _,o,_,_ in observed) if all(o is not None for _,o,_,_ in observed) else None,
                cached_input_tokens=sum(c for _,_,c,_ in observed) if all(c is not None for _,_,c,_ in observed) else None,
                budget_exceeded=(total>budget if total is not None else True if lower_bound>budget else None),
                correct_within_budget=outcome,cost=None if amount is None else str(amount))


def campaign_efficiency(runs,prices=None):
    results=[summarize_run(r,prices) for r in runs]
    success=sum(r['correct_within_budget'] is True for r in results)
    unknown=sum(r['correct_within_budget'] is None for r in results)
    tokens=sum(r['total_tokens'] for r in results) if all(r['total_tokens'] is not None for r in results) else None
    costs=sum((Decimal(r['cost']) for r in results),Decimal(0)) if all(r['cost'] is not None for r in results) else None
    return dict(runs=len(results),known_successes=success,unknown_outcomes=unknown,
                success_fraction_bounds=None if not results else [success/len(results),(success+unknown)/len(results)],
                all_run_tokens=tokens,tokens_per_success=None if not success or unknown or tokens is None else tokens/success,
                all_run_cost=None if costs is None else str(costs),
                cost_per_success=None if not success or unknown or costs is None else str(costs/Decimal(success)))


def break_even(initial_cost, saving_per_task):
    initial,saving=Decimal(str(initial_cost)),Decimal(str(saving_per_task))
    if not initial.is_finite() or not saving.is_finite() or initial<0:raise ValueError('Invalid cost/saving')
    if saving<=0:return None
    return int((initial/saving).to_integral_value(rounding=ROUND_CEILING))
