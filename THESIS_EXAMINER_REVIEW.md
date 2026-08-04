# Examiner-level review — *Static Analysis and LLMs for Verified Anti-Pattern Repair*

A different lens from the consistency review in `THESIS_REVIEW_2026-08-04.md`. That one asked whether
the thesis agrees with its artefacts. This one asks what a committee will press on: whether the design
supports the claims, whether the statistics mean what the text says they mean, and whether the
contribution survives a hostile question. The corpus-review layer is out of scope here.

Every number below is computed from `results/paired-analysis/model_ready_attempts.csv` and
`layer3/golden/`, both frozen. Nothing here needs a new run.

---

## What holds up

Worth stating first, because it is genuinely creditable and it is the platform the rest of the
argument stands on.

- **The multi-layer outcome is the thesis's best idea, and it earned its keep.** Nine repairs built
  and crossed the detector threshold yet changed frozen behaviour. A detector-only study — which is
  most of the related work — would have scored those as successes. That is a concrete demonstration
  that the field's usual endpoint is too weak, and it is the most defensible contribution in the
  document.
- **Single-shot conditions were executed independently rather than reconstructed from the first
  build of an iterative trajectory.** Most factorial designs in this space cheat here. Not cheating
  costs 228 extra calls and is the right call; §4.4.2 explains why in one clean paragraph.
- **The inferential hierarchy was pre-specified and then honoured.** Grounding, a planned secondary,
  produced the strongest effect, and §6.1.3 explicitly refuses to promote it. Examiners notice this,
  and they notice when it is missing.
- **The mixed model was not allowed to override the paired analysis** when the two disagreed. §5.4.3
  reports both random-intercept estimates and the non-convergent weak-prior fit rather than
  selecting the flattering one.
- **Intention-to-treat on the two unavailable test suites**, rather than dropping the targets.

None of the criticism below touches these. They are the reason the thesis is defensible at all.

---

## Finding 1 — The confirmatory hypothesis could not have been supported, whatever the data did

**This is the question I would open with.** The visible-test main effect is the primary estimand, and
it is tested with an exact target-level sign-flip test at α = 0.05. The reported result is +3.95 pp,
p = 0.125.

That p-value is not a near miss. It is the **floor**. Of the nineteen targets, only four produced any
difference at all between test-ON and test-OFF, and all four favoured test-ON. With four informative
clusters the exact two-sided sign-flip test cannot return anything below 0.125:

| informative clusters | smallest attainable two-sided p |
|---|---|
| 4 | 0.125 |
| 5 | 0.0625 |
| 6 | 0.03125 |
| 7 | 0.0156 |

So the direction was unanimous — 4/4 — and the test still could not reach the prespecified threshold,
because the other fifteen targets were saturated. Thirteen of nineteen targets succeeded in all
twenty-four of their attempts.

The thesis attributes the null to the interval including zero, to underpowered cells, and to
intention-to-treat dilution from the two missing suites. None of those is the dominant cause. The
cause is that the endpoint saturated, which collapsed the effective cluster count below the level at
which the chosen test can reject anything.

**This is not fatal.** A null that is explained is worth more than a null that is hand-waved, and the
unanimity of direction across every target that could move is a real, reportable finding. But it has
to be said plainly, because an examiner who works it out first will conclude the author did not.

### Proposed replacement, §5.4.2, the paragraph beginning "Visible tests added 234.4 repair tokens"

```
Two features of the design bound this result. Thirteen of the nineteen targets achieved strict
success in all twenty-four of their attempts, so they cannot contribute to any paired contrast.
Only four targets produced a difference between the test-ON and test-OFF conditions, and all four
favoured test ON. With four informative clusters the exact two-sided sign-flip test cannot return a
p-value below 0.125, which is the value reported. The prespecified threshold of 0.05 was therefore
unreachable once the outcome saturated, irrespective of how consistent the effect was. The
appropriate reading is that the direction was unanimous among the targets that could move and that
the confirmatory test lacked the resolution to act on it, rather than that the effect was absent.
Visible tests also added 234.4 repair tokens per attempt on average (95% CI +135.1 to +333.8), so
the intervention carries a measurable cost against an effect this study could not resolve.
```

### Proposed insertion, §4.8.4 (conclusion validity)

```
The confirmatory design assumed enough outcome variation across targets to support a clustered
exact test. In the executed study thirteen of nineteen targets succeeded under every condition, and
the visible-test contrast retained four informative clusters. The frozen power analysis considered
the number of targets and repetitions but not the possibility that most targets would saturate, and
this is the limitation that governs the primary result. A replication should either select targets
with a demonstrated failure rate under the weakest condition or adopt an endpoint with more
headroom, such as the ordinal repair ladder or the triggering-metric reduction, in place of a
binary success indicator.
```

---

## Finding 2 — The effective sample is six targets, and the one significant result rests on all six agreeing

The same arithmetic explains the grounding result, and here it cuts the other way.

| contrast | informative targets | signs | reported p | floor at that n |
|---|---|---|---|---|
| visible test | 4 / 19 | 4 positive, 0 negative | 0.125 | 0.125 |
| grounding | 6 / 19 | 6 positive, 0 negative | 0.03125 | 0.03125 |
| iteration | 6 / 19 | 5 positive, 1 negative | 0.21875 | 0.03125 |

Grounding reached p = 0.03125 because six targets moved and all six moved the same way. That is
again the floor: the reported significance is the statement "every target that discriminated
favoured grounding", on six targets. It is a real and coherent signal, but a reader who sees
"p = 0.031" without the cluster count will overestimate its weight, and §6.2.3's "clearest treatment
effect" and §6.4's "strongest supported intervention" both invite that reading.

Worse for the generality claim, the six informative targets are **five Long Method and one God
Class**:

```
informative   LM  AllocationCalculator.Allocate     GC  Inventory.CycleCountService
              LM  VatResolver.Resolve
              LM  RetryPolicy.NextDelay
              LM  PricingRules.ApplyAdjustments
              LM  SlotFinder.FindFirstFit
saturated     9 of 10 God Class targets, 4 of 9 Long Method targets
```

Nine of the ten God Class targets succeeded under every condition, including ungrounded single-shot,
the weakest arm in the design. So the grounding effect, the iteration effect and the visible-test
effect are all, in substance, Long Method findings with a single God Class observation attached. The
thesis reports them as results over nineteen targets spanning two anti-patterns.

### Proposed insertion, §5.4.3, before the "Grounding" subsection

```
The paired contrasts are computed over nineteen targets, but not every target contributes. A target
that achieves strict success under all eight conditions has a paired difference of zero and carries
no information about any treatment. Thirteen targets are in that position. Six targets discriminate:
AllocationCalculator.Allocate, VatResolver.Resolve, RetryPolicy.NextDelay,
PricingRules.ApplyAdjustments and SlotFinder.FindFirstFit, all Long Method, together with
Inventory.CycleCountService, the only God Class target whose outcome ever varied. Four of the six
contribute to the visible-test contrast and all six to the grounding and iteration contrasts.

The exact sign-flip p-values follow directly from those counts. Six informative clusters agreeing in
sign give p = 0.03125, which is the smallest value the test can produce at that cluster count, and
this is the grounding result. Five agreeing and one dissenting give p = 0.21875, which is the
iteration result. The grounding effect should therefore be read as unanimity of direction across the
six targets that discriminated, not as a precise estimate over nineteen. Its magnitude, +11.84
percentage points, is an average over a denominator that includes thirteen targets contributing
zero, and is consequently an attenuated summary rather than a per-target effect.
```

### Proposed replacement, §6.4, second sentence

```
The strongest supported intervention was the provision of a concise static-analysis diagnosis,
though the support is narrower than the aggregate rate suggests: nine of the ten God Class targets
and four of the nine Long Method targets succeeded under every condition, so the effect rests on
six discriminating targets, five of which are Long Method.
```

---

## Finding 3 — The grounding manipulation is not minimal, and the appendix now shows it

Grounding is the thesis's only statistically supported effect, so the purity of its manipulation
matters more than anything else in the document. §4.4.2 says the two conditions "otherwise share the
same model, source, neutral coordinates, direct-editing mechanism, and outcome procedures", and
attributes the contrast to two combined benefits: the supplied diagnosis and relief from the
diagnostic sub-task.

The prompts say otherwise. The single-shot cells use two **separately authored system prompts**, and
they differ in more than the presence of a finding:

| | grounded | ungrounded |
|---|---|---|
| framing | "repairing a supplied, already-located ... finding" | "Diagnose whether that target is a Long Method or God Class" |
| task | repair | diagnose, then repair |
| empty result | not provided for | "Use an empty findings array when no occurrence is found" |
| wording | independently written | independently written |

So the grounding factor bundles at least four things: the diagnosis, relief from diagnosis, a
differently worded task instruction, and a differently permitted output space. The last is not
cosmetic — the ungrounded model is explicitly told it may conclude there is nothing to repair, and
the grounded model is not. That is an invitation to inaction available to only one arm of the
contrast, and fourteen of the fifty-seven ungrounded single-shot attempts did fail to resolve the
detector condition.

Now that Appendix A.2 prints both prompts side by side, a reader can see this. Better to name it.

### Proposed replacement, §4.4.2, the paragraph beginning "The two contrasts have bounded interpretations"

```
The two contrasts have bounded interpretations. Grounding is realised as two separately authored
system prompts rather than as one prompt with an optional block, so the factor bundles more than the
finding itself. The grounded prompt states that the target has already been located and asks only
for a repair; the ungrounded prompt asks the model to diagnose the target before repairing it and
explicitly permits an empty findings array where no occurrence is identified. The contrast therefore
combines the supplied diagnosis, relief from the diagnostic sub-task, two independently worded task
instructions, and an output space that admits inaction in one arm but not the other. These
contributions cannot be separated in this design, and the estimate should be read as the effect of
the grounded configuration as a whole rather than of detector evidence alone. A design that isolated
the diagnosis would hold the task wording and the permitted output fixed and vary only the presence
of the finding block, as the iterative arms do (§5.1.4).
```

Note that the **iterative** arms do get this right: one system prompt, one inserted block. Saying so
turns a weakness into a demonstration that the author understood the issue, and it explains why the
grounding-by-control interaction is negative (−2.29 log-odds in the sensitivity model): the
manipulation is stronger in the single-shot arms because it carries the prompt rewrite too.

---

## Finding 4 — The private oracle's strength varies by two orders of magnitude, and ten targets record only "it ran"

Layer 3 is what makes strict success stronger than detector resolution, so its coverage is fair game.
It is a golden-file oracle: a driver exercises the target and its output is compared byte-for-byte
against a frozen file. The frozen files differ enormously in what they pin down.

```
10 targets   7 bytes    EXEC_OK              all ten Obsolete API Usage instances
 1 target   30 bytes    4 recorded values    PricingRules.ApplyAdjustments
 …
 1 target  729 bytes   33 recorded values    Inventory.StockController
```

All ten Obsolete API goldens are the identical seven-byte string `EXEC_OK`. §4.5.5 does say the
instrument reduces to an execution check for that category, so this is disclosed rather than hidden.
What is not disclosed is the spread within the categories the thesis does treat as equivalence
oracles. A Layer 3 pass on `PricingRules.ApplyAdjustments` pins four values; a pass on
`Inventory.StockController` pins thirty-three. Both count identically towards 447/456.

This matters for two claims. First, "447 of 456 passed the private behavioural oracle" reads as a
uniform standard and is not one. Second, Table 5.12 in the supplement reports a single "Layer 3 pass"
column over thirty targets, ten of which can only ever record `EXEC_OK`, so an equivalence result and
a liveness result are added together.

### Proposed insertion, §4.5.5, after the "Obsolete-API repairs" paragraph

```
The instrument's resolving power varies across targets. Each driver records the observable output it
produces on fixed inputs, and the frozen baseline ranges from four recorded values for the smallest
Long Method target to thirty-three for the largest God Class target. The ten Obsolete API Usage
baselines record only that execution completed. A pass therefore establishes preservation over a
larger behavioural surface for some targets than for others, and the aggregate pass count should be
read with that in mind. Table X reports the baseline size per target so that a reader can weigh each
result.
```

### Proposed change to Table 5.12

Split the Layer 3 column into equivalence outcomes over God Class and Long Method and smoke outcomes
over Obsolete API Usage, rather than reporting one figure over all thirty. The underlying data
already supports the split; the thesis reports the distinction in prose at §5.4.8 but not in the
table a reader will quote.

---

## Finding 5 — RQ3 is reported as a null when it is unanswerable for two of three anti-patterns

Verified repair in the supplement: God Class 0/10 at every context level, Obsolete API Usage 0/10 at
Minimal and Structural, 2/10 and 1/10 at Relational and Full with none passing the smoke oracle.
Long Method 9, 8, 9, 8.

So the context question was answered on Long Method and nothing else. The God Class rate is zero
across all four levels because the fixed applier rejected the recommendations as insufficiently
specified — a property of the applier, not of context. §5.4.5 and §6.2.4 both say this, and then both
conclude that context granularity has no reliable monotonic effect.

That conclusion is sound for Long Method and unsupported for the other two. An examiner will ask what
would have happened at 0/10 versus 0/10: nothing can be inferred from a contrast between two floors.

### Proposed replacement, §6.2.4, closing paragraph

```
The supplement's reach is narrower than its aggregate rate implies. God Class produced no verified
repair at any context level, because the fixed applier judged every recommendation insufficiently
specified, and Obsolete API Usage produced three detector-resolved migrations in total, none of which
passed the smoke oracle. A comparison between two floors carries no information, so the four-level
result is a Long Method finding: for that category, context beyond a concise diagnosis did not change
verified repair. For God Class the experiment measures the applier's tolerance for abstract
recommendations rather than the value of context, and for Obsolete API Usage it measures the
difficulty of a behaviour-modifying migration. Both remain open.
```

---

## Finding 6 — No multiplicity adjustment across the three main effects, and the reader is entitled to the sensitivity

Holm is applied within the cell-specific and interaction families. The three main effects — visible
test, grounding, iteration — are reported unadjusted, which the prespecified hierarchy permits
because only one is confirmatory and the others are labelled planned secondary. That is a defensible
position and it is the position the thesis takes.

It is also the position an examiner will test, because the only significant result in the thesis sits
in the unadjusted secondary family. Holm across the three would give 0.03125 × 3 = 0.094. Stating
this pre-emptively costs a sentence and removes the question.

### Proposed insertion, §4.6, after the paragraph on the confirmatory contrast

```
The three main effects are not adjusted against one another. The hierarchy assigns one confirmatory
estimand and two planned secondary estimands before any outcome was inspected, and adjustment within
that structure is not required. Reported for transparency: Holm adjustment across the three main
effects would raise the grounding p-value from 0.03125 to 0.094, so a reader who prefers a single
undifferentiated family of three tests would not treat the grounding result as significant at 0.05.
The prespecified hierarchy is retained, and the grounding effect is reported as a planned secondary
result rather than as a confirmatory one throughout.
```

---

## Finding 7 — RQ4 is not a research question

"After repair, what changes are observed in triggering metrics, whole-solution detector and
CodeAnalyzer diagnostics, independent private behaviour, and computational cost?" — every possible
observation answers it. There is no way for RQ4 to come out one way rather than another, so it cannot
be supported or refuted, and §6.2.5 accordingly reports numbers rather than reaching a finding.

The material under RQ4 is worth keeping; the framing is not. Two options.

The lighter fix is to demote it: fold the whole-solution and cost measures into RQ1's
operationalisation as secondary outcomes, and drop the RQ numbering. The thesis already treats them
that way in §4.5.

The better fix is to give it a claim it could fail:

```
RQ4 (multi-layer repair quality) Does a repair that resolves its triggering detector condition leave
the rest of the solution no worse by independent measurement, and at what resource cost?
```

That version is answerable, and the answer is interesting: mostly yes by the all-rules count
(−106) and no by the enabled-by-default headline count (+46, entirely Performance). The thesis
already has that result in §5.4.7; it just is not currently the answer to anything.

---

## Finding 8 — Corpus difficulty was not calibrated, and this is the root cause of Findings 1 and 2

Thirteen of nineteen targets succeeded under every condition, nine of ten God Class targets among
them. The corpus was verified for *detectability* — every seeded instance measures inside its
intended metric band — but never for *difficulty*, meaning the property that some conditions should
fail on it. Those are different requirements, and only the first was checked before the freeze.

This connects to a finding from the corpus review: GC-09, LM-08 and LM-10 sit one or two units above
their detection thresholds and each contains unreachable branches whose deletion alone carries the
instance below the bound. If a repair can cross the threshold by deleting dead code, near-ceiling
success rates are unsurprising.

### Proposed insertion, §4.8.2 (construct validity)

```
The corpus was verified for detectability but not for difficulty. Every seeded instance measures
inside its intended stratum band, which establishes that the detector and the treatments received
the intended inputs; it does not establish that the instances are hard enough to separate the
conditions. In the executed study thirteen of nineteen confirmatory targets succeeded under every
condition, so most of the corpus exerted no discriminating pressure. Several borderline instances
also sit one or two units above their detection bound and contain unreachable branches whose removal
alone would carry the measured value below it, so a metric-resolved verdict on those instances is
compatible with branch simplification rather than the intended refactoring. A corpus intended to
compare repair configurations should be piloted under the weakest configuration and calibrated to a
target failure rate before it is frozen.
```

### The analysis that would close this

You have all 456 archived final sources and their unified diffs. Classifying each into "extracted a
type or method" versus "removed or simplified branches only" is a mechanical diff analysis over
existing artefacts, with no model calls. If the grounded cells genuinely extracted, Finding 8 becomes
a stated limitation with evidence against it, and §4.5.2's gaming guard is discharged rather than
hedged. If some repairs only simplified branches, that is a result in itself and belongs in §5.4.7.
Either outcome strengthens the thesis. I would do this before submission.

---

## The five questions I would ask in the viva

1. Your primary hypothesis returned p = 0.125. With four informative clusters, what is the smallest
   p your test could have returned, and what does that tell us about the design?
2. How many of your nineteen targets contributed to the grounding estimate, and what were their signs?
3. Your grounded and ungrounded single-shot prompts are different documents. What else varies with
   grounding besides the finding block?
4. A Layer 3 pass on your smallest target compares four recorded values. On what basis do you treat
   that as equivalent evidence to a pass on your largest?
5. God Class produced 0/10 verified repair at all four context levels. What does the comparison
   between those levels tell us?

Every one of them has a good answer available from data already on disk. None of them has a good
answer if it is heard for the first time in the room.

---

## Priority

| | item | effort |
|---|---|---|
| 1 | Findings 1 and 2 — the cluster-count reframing in §5.4.2, §5.4.3, §6.4, §4.8.4 | half a day, no new data |
| 2 | Finding 3 — the grounding manipulation in §4.4.2 | an hour |
| 3 | Finding 8 — the extraction-versus-simplification analysis | an afternoon |
| 4 | Findings 4 and 5 — oracle spread in §4.5.5 and Table 5.12; RQ3 reframing in §6.2.4 | half a day |
| 5 | Findings 6 and 7 — multiplicity sentence in §4.6; RQ4 rewording | an hour |

Findings 1 and 2 are the ones that change what the thesis claims. The rest are hardening.

None of this requires re-running a campaign, and none of it weakens the contribution. A thesis that
reports a saturated endpoint, names the six targets its effects rest on, and explains why its
primary test could not reject is a more convincing document than one reporting +11.84 pp and
p = 0.031 without that context — because the first has clearly been read by its author with the same
scepticism a committee will bring.
