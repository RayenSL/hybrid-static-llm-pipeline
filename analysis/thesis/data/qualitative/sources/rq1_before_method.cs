    public AccessDecision Decide(Principal? principal, Resource? resource, AccessRequest? request, IDelegationRegister delegations)
    {
        if (principal is null || resource is null || request is null)
            return new AccessDecision(false, "missing-context", true);
        if (string.IsNullOrWhiteSpace(principal.Id) || string.IsNullOrWhiteSpace(resource.Id))
            return new AccessDecision(false, "invalid-identity", true);
        if (principal.Suspended)
            return new AccessDecision(false, "principal-suspended", true);
        if (!string.Equals(principal.TenantId, resource.TenantId, StringComparison.Ordinal))
            return new AccessDecision(false, "tenant-mismatch", true);
        if (resource.Locked && request.Action != "read")
            return new AccessDecision(false, "resource-locked", true);
        if (request.MinuteOfDay is < 0 or > 1439)
            return new AccessDecision(false, "invalid-time", true);
        if (principal.FailedChallenges >= 3 && !request.StrongAuthentication)
            return new AccessDecision(false, "challenge-required", true);

        var administrator = principal.Roles.Contains("administrator");
        var operatorRole = principal.Roles.Contains("operator");
        var auditor = principal.Roles.Contains("auditor");
        var owner = principal.Id == resource.OwnerId;
        var delegated = delegations.HasDelegation(principal.Id, resource.Id, request.Action);

        if (request.BreakGlass)
        {
            if (!administrator || !request.StrongAuthentication)
                return new AccessDecision(false, "invalid-break-glass", true);
            return new AccessDecision(true, "break-glass", true);
        }
        if (resource.Classification == "restricted" && !request.StrongAuthentication)
            return new AccessDecision(false, "strong-authentication-required", true);
        if (resource.Classification == "restricted" && request.NetworkZone != "trusted")
            return new AccessDecision(false, "trusted-network-required", true);
        if (request.Action == "delete" && !administrator)
            return new AccessDecision(false, "administrator-required", true);
        if (request.Action == "write" && !(administrator || operatorRole || owner || delegated))
            return new AccessDecision(false, "write-not-authorised", true);
        if (request.Action == "read" && !(administrator || operatorRole || auditor || owner || delegated))
            return new AccessDecision(false, "read-not-authorised", false);
        if (request.Action is not ("read" or "write" or "delete"))
            return new AccessDecision(false, "unknown-action", true);

        var outsideBusinessHours = request.MinuteOfDay < 480 || request.MinuteOfDay > 1080;
        return new AccessDecision(true, delegated ? "delegated" : "role-or-ownership", outsideBusinessHours || resource.Classification == "restricted");
    }
