# Repair shape: extraction against branch simplification

Classified 456 archived repairs from their frozen unified diffs. No model calls; outcomes joined from `attempts.json`.

## Overall

| Shape | n | share |
|---|---:|---:|
| extract_type | 239 | 52.4% |
| extract_method | 193 | 42.3% |
| no_change | 24 | 5.3% |

## The gaming question

- metric-resolved repairs: **432**
- of those, repairs that introduced no new method or type: **0** (0.0%)
- of those, classified `simplify_only`: **0**
- metric-unresolved repairs: 24

## Where the non-repairs fall

Every unresolved attempt is a non-repair: the model returned the pristine source unchanged and reported an empty findings array. None is a failed edit.

| Stratum | attempts | non-repairs | rate |
|---|---:|---:|---:|
| clear_cut | 216 | 0 | 0.0% |
| borderline | 240 | 24 | 10.0% |

| Grounding | Control | attempts | non-repairs |
|---|---|---:|---:|
| ungrounded | single_shot | 114 | 23 |
| ungrounded | iterative | 114 | 1 |
| grounded | single_shot | 114 | 0 |
| grounded | iterative | 114 | 0 |

## By arm

| Grounding | Control | Test | extract_type | extract_method | simplify_only | other_edit | no_change | extraction rate |
|---|---|---|---:|---:|---:|---:|---:|---:|
| ungrounded | single_shot | OFF | 29 | 14 | 0 | 0 | 14 | 75.4% |
| ungrounded | single_shot | ON | 30 | 18 | 0 | 0 | 9 | 84.2% |
| ungrounded | iterative | OFF | 30 | 26 | 0 | 0 | 1 | 98.2% |
| ungrounded | iterative | ON | 30 | 27 | 0 | 0 | 0 | 100.0% |
| grounded | single_shot | OFF | 30 | 27 | 0 | 0 | 0 | 100.0% |
| grounded | single_shot | ON | 30 | 27 | 0 | 0 | 0 | 100.0% |
| grounded | iterative | OFF | 30 | 27 | 0 | 0 | 0 | 100.0% |
| grounded | iterative | ON | 30 | 27 | 0 | 0 | 0 | 100.0% |

## By anti-pattern

| Pattern | n | extract_type | extract_method | simplify_only | other_edit | no_change | mean new methods | mean new types |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| god_class | 240 | 239 | 0 | 0 | 0 | 1 | 8.39 | 4.09 |
| long_method | 216 | 0 | 193 | 0 | 0 | 23 | 3.10 | 0.00 |

## Per target

| Target | Pattern | n | extraction | simplify_only | other | mean branches removed |
|---|---|---:|---:|---:|---:|---:|
| `AllocationCalculator.Allocate` | long_method | 24 | 21 | 0 | 3 | 5.1 |
| `DispatchPipeline.Run` | long_method | 24 | 24 | 0 | 0 | 4.0 |
| `Inventory.CycleCountService` | god_class | 24 | 23 | 0 | 1 | 14.4 |
| `Inventory.StockController` | god_class | 24 | 24 | 0 | 0 | 18.2 |
| `InvoiceRenderer.Render` | long_method | 24 | 24 | 0 | 0 | 5.0 |
| `Invoicing.BillingManager` | god_class | 24 | 24 | 0 | 0 | 18.3 |
| `Invoicing.StatementBuilder` | god_class | 24 | 24 | 0 | 0 | 19.1 |
| `Notifications.NotificationCenter` | god_class | 24 | 24 | 0 | 0 | 13.5 |
| `Ordering.CheckoutCoordinator` | god_class | 24 | 24 | 0 | 0 | 12.3 |
| `Ordering.OrderProcessor` | god_class | 24 | 24 | 0 | 0 | 12.3 |
| `Ordering.ReturnsHandler` | god_class | 24 | 24 | 0 | 0 | 21.0 |
| `PricingRules.ApplyAdjustments` | long_method | 24 | 22 | 0 | 2 | 3.2 |
| `ReplenishmentPlanner.BuildPlan` | long_method | 24 | 24 | 0 | 0 | 12.7 |
| `RetryPolicy.NextDelay` | long_method | 24 | 18 | 0 | 6 | 5.4 |
| `Scheduler.PlaceJobs` | long_method | 24 | 24 | 0 | 0 | 9.3 |
| `Scheduling.RecurrenceEngine` | god_class | 24 | 24 | 0 | 0 | 17.3 |
| `Scheduling.ScheduleManager` | god_class | 24 | 24 | 0 | 0 | 29.6 |
| `SlotFinder.FindFirstFit` | long_method | 24 | 17 | 0 | 7 | 4.7 |
| `VatResolver.Resolve` | long_method | 24 | 19 | 0 | 5 | 6.3 |
