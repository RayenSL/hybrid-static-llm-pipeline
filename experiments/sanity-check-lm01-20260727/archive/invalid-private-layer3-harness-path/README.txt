INVALID INSTRUMENTATION OUTPUT — DO NOT ANALYSE

The first private Layer-3 invocation copied the characterization harness to
<working-root>/characterization while its frozen project references require it
at <working-root>/src/characterization. All eight executions failed to compile,
with passing_drivers=0 and failing_drivers=0. No behavioral oracle driver ran.
The repair artifacts were not changed and no result was returned to any model.
The evaluator placement was fixed, regression-tested, and the private evaluation
was rerun from the same frozen final-source artifacts.
