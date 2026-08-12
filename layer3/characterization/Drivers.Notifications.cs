namespace Characterization;

using System.Globalization;
using System.Text;
using Notifications;

// Characterisation drivers for the Notifications module (Layer-3 behavioural instrument).
//   - God Class / Long Method  -> golden-master (deterministic, labelled, InvariantCulture)
//   - Obsolete API             -> smoke (call as-is, return "EXEC_OK")
internal static class NotificationsDrivers
{
    public static readonly (string Key, System.Func<string> Drive)[] All = new (string, System.Func<string>)[]
    {
        ("Notifications.NotificationCenter", NotificationCenter),
        ("DispatchPipeline.Run", DispatchPipeline_Run),
        ("RetryPolicy.NextDelay", RetryPolicy_NextDelay),
        ("EmailClient.SendEmail", EmailClient_SendEmail),
        ("PushClient.SendPush", PushClient_SendPush),
        ("SmsClient.SendSms", SmsClient_SendSms),
    };

    // Builds a fixed Message; every field is deterministic.
    static Message Msg(Channel channel, string subject, string body,
                       string name = "Ada", string email = "", string phone = "")
        => new Message
        {
            Channel = channel,
            Subject = subject,
            Body = body,
            Recipient = new Recipient { Name = name, EmailAddress = email, Phone = phone },
        };

    // ── God Class: drive Route, ResolveChannel, Render, CacheRender and Track across
    //    fixed scenarios that hit the distinguishing branches of each public method. ──
    static string NotificationCenter()
    {
        var sb = new StringBuilder();

        // Route — fresh instance so route/delivery state is deterministic.
        var routeCenter = new Notifications.NotificationCenter();
        sb.Append("Route.emailMissing=").Append(routeCenter.Route(Msg(Channel.Email, "s", "b", email: ""))).Append('\n');
        sb.Append("Route.push=").Append(routeCenter.Route(Msg(Channel.Push, "s", "b", email: "p@x.com"))).Append('\n');
        sb.Append("Route.sms=").Append(routeCenter.Route(Msg(Channel.Sms, "s", "b", email: "s@x.com", phone: "12345"))).Append('\n');
        sb.Append("Route.email=").Append(routeCenter.Route(Msg(Channel.Email, "s", "b", email: "e@x.com"))).Append('\n');
        sb.Append("Route.emailDuplicate=").Append(routeCenter.Route(Msg(Channel.Email, "s", "b", email: "e@x.com"))).Append('\n');

        // ResolveChannel — fresh instance (route counts all zero).
        var resolveCenter = new Notifications.NotificationCenter();
        sb.Append("Resolve.email=").Append(resolveCenter.ResolveChannel(Msg(Channel.Email, "s", "b"))).Append('\n');
        sb.Append("Resolve.sms=").Append(resolveCenter.ResolveChannel(Msg(Channel.Sms, "s", "b"))).Append('\n');
        sb.Append("Resolve.push=").Append(resolveCenter.ResolveChannel(Msg(Channel.Push, "s", "b"))).Append('\n');

        // Render — fresh instance + concrete corpus ITemplateStore.
        var templates = new InMemoryTemplateStore();
        templates.Set("welcome", "Hi {body}");
        templates.Set("empty-template", "");
        var renderCenter = new Notifications.NotificationCenter();
        sb.Append("Render.noSubject=[").Append(renderCenter.Render(Msg(Channel.Email, "", "b"), templates)).Append("]\n");
        sb.Append("Render.template=[").Append(renderCenter.Render(Msg(Channel.Email, "welcome", "hello"), templates)).Append("]\n");
        sb.Append("Render.noTemplate=[").Append(renderCenter.Render(Msg(Channel.Email, "missing", "plain"), templates)).Append("]\n");
        sb.Append("Render.emptyBody=[").Append(renderCenter.Render(Msg(Channel.Email, "greeting", ""), templates)).Append("]\n");
        sb.Append("Render.cachedTemplate=[").Append(renderCenter.Render(Msg(Channel.Email, "welcome", "IGNORED-CACHED"), templates)).Append("]\n");

        // CacheRender — fresh instance; exercise reject/accept branches.
        var cacheCenter = new Notifications.NotificationCenter();
        sb.Append("Cache.noSubject=").Append(cacheCenter.CacheRender(Msg(Channel.Email, "", "content"), "content").ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("Cache.emptyContent=").Append(cacheCenter.CacheRender(Msg(Channel.Email, "k", ""), "").ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("Cache.singleChar=").Append(cacheCenter.CacheRender(Msg(Channel.Email, "k", "x"), "x").ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("Cache.accepted=").Append(cacheCenter.CacheRender(Msg(Channel.Email, "k", "hello world"), "hello world").ToString(CultureInfo.InvariantCulture)).Append('\n');
        sb.Append("Cache.errPrefix=").Append(cacheCenter.CacheRender(Msg(Channel.Email, "k2", "ERRxx"), "ERRxx").ToString(CultureInfo.InvariantCulture)).Append('\n');

        // Track — fresh instance; delivered / failed / overflow branches.
        var trackCenter = new Notifications.NotificationCenter();
        sb.Append("Track.noKey=").Append(trackCenter.Track(Msg(Channel.Email, "s", "b", email: ""), true)).Append('\n');
        sb.Append("Track.deliveredFirst=").Append(trackCenter.Track(Msg(Channel.Email, "s", "b", email: "t1@x.com"), true)).Append('\n');
        sb.Append("Track.failed=").Append(trackCenter.Track(Msg(Channel.Email, "s", "b", email: "t2@x.com"), false)).Append('\n');
        sb.Append("Track.deliveredAgain=").Append(trackCenter.Track(Msg(Channel.Email, "s", "b", email: "t1@x.com"), true));

        return sb.ToString();
    }

    // ── Long Method: DispatchPipeline.Run — fixed scenarios over each guard/branch. ──
    static string DispatchPipeline_Run()
    {
        var templates = new InMemoryTemplateStore();
        templates.Set("welcome", "T:");
        var unsubscribed = new UnsubscribeList();
        unsubscribed.Add("gone@x.com");
        var pipeline = new DispatchPipeline(templates, unsubscribed);

        var sb = new StringBuilder();
        sb.Append("emptyBody=").Append(pipeline.Run(Msg(Channel.Email, "welcome", "", email: "e@x.com"), 0)).Append('\n');
        sb.Append("invalidEmail=").Append(pipeline.Run(Msg(Channel.Email, "welcome", "hi", email: "noat"), 0)).Append('\n');
        sb.Append("invalidPhone=").Append(pipeline.Run(Msg(Channel.Sms, "welcome", "hi", phone: "12"), 0)).Append('\n');
        sb.Append("unsubscribed=").Append(pipeline.Run(Msg(Channel.Email, "welcome", "hi", email: "gone@x.com"), 0)).Append('\n');
        sb.Append("throttled=").Append(pipeline.Run(Msg(Channel.Email, "welcome", "hi", email: "e@x.com"), 6)).Append('\n');
        sb.Append("noTemplate=").Append(pipeline.Run(Msg(Channel.Email, "missing", "hi", email: "e@x.com"), 0)).Append('\n');
        sb.Append("sentEmail=").Append(pipeline.Run(Msg(Channel.Email, "welcome", "hi", email: "e@x.com"), 0)).Append('\n');
        sb.Append("retryEmail=").Append(pipeline.Run(Msg(Channel.Email, "welcome", "hi", email: "e@x.com"), 2)).Append('\n');
        sb.Append("sentSms=").Append(pipeline.Run(Msg(Channel.Sms, "welcome", "body", phone: "12345"), 0)).Append('\n');
        sb.Append("sentPush=").Append(pipeline.Run(Msg(Channel.Push, "welcome", "body", email: "e@x.com"), 0));
        return sb.ToString();
    }

    // ── Long Method: RetryPolicy.NextDelay — pure function; fixed input grid. ──
    static string RetryPolicy_NextDelay()
    {
        var policy = new RetryPolicy();
        (string Label, int Attempt, Channel Channel, bool Busy)[] cases =
        {
            ("zeroAttempt",   0,  Channel.Email, false),
            ("overCap",       11, Channel.Email, false),
            ("emailNoBusy",   2,  Channel.Email, false),
            ("smsBusy",       3,  Channel.Sms,   true),
            ("pushHighAttempt", 8, Channel.Push, false),
            ("emailBusyHigh", 9,  Channel.Email, true),
            ("belowBoundary",  1, Channel.Email, false),
            ("atBoundary",     5, Channel.Email, false),
            ("alternateSms",   2, Channel.Sms, false),
            ("repeatEmail",    2, Channel.Email, false),
        };

        var sb = new StringBuilder();
        for (var i = 0; i < cases.Length; i++)
        {
            var c = cases[i];
            var delay = policy.NextDelay(c.Attempt, c.Channel, c.Busy);
            sb.Append(c.Label).Append('=').Append(delay.ToString(CultureInfo.InvariantCulture));
            if (i < cases.Length - 1) sb.Append('\n');
        }
        return sb.ToString();
    }

    // ── Obsolete API smokes: call the public method as-is (it invokes the [Obsolete]
    //    legacy API internally); return the constant marker without serialising output. ──
    static string EmailClient_SendEmail()
    {
        var client = new EmailClient();
        client.SendEmail(Msg(Channel.Email, "welcome", "body", email: "e@x.com"));
        return "EXEC_OK";
    }

    static string PushClient_SendPush()
    {
        var client = new PushClient();
        client.SendPush(Msg(Channel.Push, "welcome", "body", name: "device-1"));
        return "EXEC_OK";
    }

    static string SmsClient_SendSms()
    {
        var client = new SmsClient();
        client.SendSms(Msg(Channel.Sms, "welcome", "body", phone: "12345"));
        return "EXEC_OK";
    }
}
