return args[0] switch {
    "--probe" => GenericProbe.Run(args),
    "--facts" => ExpandedFacts.Run(args),
    "--context" => ExpandedFacts.Context(args),
    "--audit" => CandidateAudit.Run(args),
    _ => CandidateEvaluator.Run(args)
};
