namespace AccessControl;

public sealed class AccessDecisionEngine
{
    public AccessDecision Decide(Principal? principal, Resource? resource, AccessRequest? request, IDelegationRegister delegations)
    {
        if (principal is null || resource is null || request is null)
            return Deny("missing-context");

        var validationFailure = ValidatePrincipalAndResource(principal, resource, request);
        if (validationFailure is not null)
            return validationFailure;

        validationFailure = ValidateRequest(principal, request);
        if (validationFailure is not null)
            return validationFailure;

        var administrator = principal.Roles.Contains("administrator");
        var operatorRole = principal.Roles.Contains("operator");
        var auditor = principal.Roles.Contains("auditor");
        var owner = principal.Id == resource.OwnerId;
        var delegated = delegations.HasDelegation(principal.Id, resource.Id, request.Action);

        if (request.BreakGlass)
            return DecideBreakGlass(administrator, request.StrongAuthentication);

        var classificationFailure = ValidateClassification(resource, request);
        if (classificationFailure is not null)
            return classificationFailure;

        return DecideAction(
            resource,
            request,
            administrator,
            operatorRole,
            auditor,
            owner,
            delegated);
    }

    private static AccessDecision? ValidatePrincipalAndResource(
        Principal principal,
        Resource resource,
        AccessRequest request)
    {
        if (string.IsNullOrWhiteSpace(principal.Id) || string.IsNullOrWhiteSpace(resource.Id))
            return Deny("invalid-identity");
        if (principal.Suspended)
            return Deny("principal-suspended");
        if (!string.Equals(principal.TenantId, resource.TenantId, StringComparison.Ordinal))
            return Deny("tenant-mismatch");
        if (resource.Locked && request.Action != "read")
            return Deny("resource-locked");

        return null;
    }

    private static AccessDecision? ValidateRequest(Principal principal, AccessRequest request)
    {
        if (request.MinuteOfDay is < 0 or > 1439)
            return Deny("invalid-time");
        if (principal.FailedChallenges >= 3 && !request.StrongAuthentication)
            return Deny("challenge-required");

        return null;
    }

    private static AccessDecision DecideBreakGlass(bool administrator, bool strongAuthentication)
    {
        return administrator && strongAuthentication
            ? new AccessDecision(true, "break-glass", true)
            : Deny("invalid-break-glass");
    }

    private static AccessDecision? ValidateClassification(Resource resource, AccessRequest request)
    {
        if (resource.Classification != "restricted")
            return null;
        if (!request.StrongAuthentication)
            return Deny("strong-authentication-required");
        if (request.NetworkZone != "trusted")
            return Deny("trusted-network-required");

        return null;
    }

    private static AccessDecision DecideAction(
        Resource resource,
        AccessRequest request,
        bool administrator,
        bool operatorRole,
        bool auditor,
        bool owner,
        bool delegated)
    {
        switch (request.Action)
        {
            case "delete":
                if (!administrator)
                    return Deny("administrator-required");
                break;
            case "write":
                if (!CanWrite(administrator, operatorRole, owner, delegated))
                    return Deny("write-not-authorised");
                break;
            case "read":
                if (!CanRead(administrator, operatorRole, auditor, owner, delegated))
                    return new AccessDecision(false, "read-not-authorised", false);
                break;
            default:
                return Deny("unknown-action");
        }

        var outsideBusinessHours = request.MinuteOfDay < 480 || request.MinuteOfDay > 1080;
        var auditRequired = outsideBusinessHours || resource.Classification == "restricted";
        return new AccessDecision(true, delegated ? "delegated" : "role-or-ownership", auditRequired);
    }

    private static bool CanWrite(bool administrator, bool operatorRole, bool owner, bool delegated)
    {
        return administrator || operatorRole || owner || delegated;
    }

    private static bool CanRead(bool administrator, bool operatorRole, bool auditor, bool owner, bool delegated)
    {
        return administrator || operatorRole || auditor || owner || delegated;
    }

    private static AccessDecision Deny(string reason)
    {
        return new AccessDecision(false, reason, true);
    }
}
