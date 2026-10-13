using System;
using System.Linq;
using System.Text.Json.Nodes;

namespace Jellyfin.Plugin.EpgStation.EpgStation;

/// <summary>
/// One genre condition of a rule (ARIB genre, optional sub genre).
/// </summary>
public class RuleGenre
{
    /// <summary>Gets or sets the ARIB genre (0-15).</summary>
    public int Genre { get; set; }

    /// <summary>Gets or sets the ARIB sub genre (0-15), or null for the whole genre.</summary>
    public int? SubGenre { get; set; }
}

/// <summary>
/// One weekday/time window of a rule.
/// </summary>
public class RuleTime
{
    /// <summary>Gets or sets the weekdays: 0x01 Sunday ... 0x40 Saturday, or-ed.</summary>
    public int Week { get; set; }

    /// <summary>Gets or sets the start hour (0-23), or null for all day.</summary>
    public int? Start { get; set; }

    /// <summary>Gets or sets the window length in hours (1-23), or null for all day.</summary>
    public int? Range { get; set; }
}

/// <summary>
/// The rule fields the plugin's editor shows. Everything else on an existing rule is kept.
/// </summary>
public class RuleEdit
{
    /// <summary>Gets or sets the search keyword ("" = none: then genres are required).</summary>
    public string Keyword { get; set; } = string.Empty;

    /// <summary>Gets or sets the words to exclude.</summary>
    public string IgnoreKeyword { get; set; } = string.Empty;

    /// <summary>Gets or sets a value indicating whether keyword and exclusions also search the description.</summary>
    public bool FullText { get; set; }

#pragma warning disable CA1819 // JSON DTO
    /// <summary>Gets or sets the broadcast types (GR, BS, CS, SKY); used when no channel is given.</summary>
    public string[] Types { get; set; } = [];

    /// <summary>Gets or sets specific channels (EPGStation channel ids); overrides <see cref="Types"/>.</summary>
    public long[] ChannelIds { get; set; } = [];

    /// <summary>Gets or sets the genre conditions (empty = any genre).</summary>
    public RuleGenre[] Genres { get; set; } = [];

    /// <summary>Gets or sets the weekday/time windows (empty = any time).</summary>
    public RuleTime[] Times { get; set; } = [];
#pragma warning restore CA1819

    /// <summary>Gets or sets a value indicating whether only free programmes match.</summary>
    public bool IsFree { get; set; }

    /// <summary>Gets or sets a value indicating whether the rule is enabled.</summary>
    public bool Enable { get; set; } = true;

    /// <summary>Gets or sets a value indicating whether already recorded programmes are skipped.</summary>
    public bool AvoidDuplicate { get; set; }

    /// <summary>Gets or sets the days to look back for duplicates (0 = EPGStation default, null = keep the rule's).</summary>
    public int? PeriodToAvoidDuplicate { get; set; }
}

/// <summary>
/// Builds EPGStation rule JSON from <see cref="RuleEdit"/>, keeping fields the editor doesn't show.
/// </summary>
public static class RuleBuilder
{
    private static readonly string[] BroadcastTypes = ["GR", "BS", "CS", "SKY"];

    /// <summary>
    /// Checks an edit. Returns an error code for the page, or null when it is fine.
    /// </summary>
    /// <param name="edit">The edit.</param>
    /// <returns>Error code or null.</returns>
    public static string? Validate(RuleEdit edit)
    {
        ArgumentNullException.ThrowIfNull(edit);
        if (edit.Keyword.Length > 200 || edit.IgnoreKeyword.Length > 200)
        {
            return "RuleInvalid";
        }

        // Without a keyword or a genre a rule matches everything on the chosen channels.
        if (edit.Keyword.Trim().Length == 0 && edit.Genres.Length == 0)
        {
            return "RuleNeedsKeywordOrGenre";
        }

        if (edit.ChannelIds.Length == 0 && !edit.Types.Any(BroadcastTypes.Contains))
        {
            return "RuleNeedsScope";
        }

        if (edit.ChannelIds.Length > 500 || edit.ChannelIds.Any(c => c <= 0)
            || edit.Genres.Any(g => g.Genre is < 0 or > 15 || g.SubGenre is < 0 or > 15)
            || edit.Times.Length > 20
            || edit.Times.Any(t => t.Week is < 1 or > 0x7f
                || (t.Start is null) != (t.Range is null)
                || t.Start is < 0 or > 23 || t.Range is < 1 or > 23)
            || edit.PeriodToAvoidDuplicate is < 0 or > 3650)
        {
            return "RuleInvalid";
        }

        return null;
    }

    /// <summary>
    /// The rule's searchOption: <paramref name="existing"/> (kept options such as regex or duration
    /// limits) with the editor's fields applied.
    /// </summary>
    /// <param name="edit">The edit (validated).</param>
    /// <param name="existing">The rule's current searchOption, or null for a new rule.</param>
    /// <returns>The new searchOption.</returns>
    public static JsonObject SearchOption(RuleEdit edit, JsonObject? existing)
    {
        ArgumentNullException.ThrowIfNull(edit);
        var o = existing?.DeepClone().AsObject() ?? [];

        foreach (var k in new[] { "keyword", "name", "description", "extended" })
        {
            o.Remove(k);
        }

        var keyword = edit.Keyword.Trim();
        if (keyword.Length > 0)
        {
            o["keyword"] = keyword;
            o["name"] = true;
            o["description"] = edit.FullText;
            o["extended"] = edit.FullText;
        }
        else
        {
            o.Remove("keyCS");
            o.Remove("keyRegExp");
        }

        foreach (var k in new[] { "ignoreKeyword", "ignoreName", "ignoreDescription", "ignoreExtended" })
        {
            o.Remove(k);
        }

        var ignore = edit.IgnoreKeyword.Trim();
        if (ignore.Length > 0)
        {
            o["ignoreKeyword"] = ignore;
            o["ignoreName"] = true;
            o["ignoreDescription"] = edit.FullText;
            o["ignoreExtended"] = edit.FullText;
        }
        else
        {
            o.Remove("ignoreKeyCS");
            o.Remove("ignoreKeyRegExp");
        }

        // EPGStation refuses channelIds together with a broadcast type flag.
        o.Remove("channelIds");
        foreach (var t in BroadcastTypes)
        {
            o.Remove(t);
        }

        if (edit.ChannelIds.Length > 0)
        {
            o["channelIds"] = new JsonArray(edit.ChannelIds.Distinct().Select(c => (JsonNode)c).ToArray());
        }
        else
        {
            foreach (var t in BroadcastTypes)
            {
                o[t] = edit.Types.Contains(t);
            }
        }

        o.Remove("genres");
        if (edit.Genres.Length > 0)
        {
            o["genres"] = new JsonArray(edit.Genres.Select(g =>
            {
                var n = new JsonObject { ["genre"] = g.Genre };
                if (g.SubGenre is int sub)
                {
                    n["subGenre"] = sub;
                }

                return (JsonNode)n;
            }).ToArray());
        }

        o.Remove("times");
        if (edit.Times.Length > 0)
        {
            o["times"] = new JsonArray(edit.Times.Select(t =>
            {
                var n = new JsonObject { ["week"] = t.Week };
                if (t.Start is int start && t.Range is int range)
                {
                    n["start"] = start;
                    n["range"] = range;
                }

                return (JsonNode)n;
            }).ToArray());
        }

        if (edit.IsFree)
        {
            o["isFree"] = true;
        }
        else
        {
            o.Remove("isFree");
        }

        return o;
    }

    /// <summary>
    /// The rule's reserveOption: <paramref name="existing"/> (kept: tags, end lack) with the
    /// editor's fields applied.
    /// </summary>
    /// <param name="edit">The edit (validated).</param>
    /// <param name="existing">The rule's current reserveOption, or null for a new rule.</param>
    /// <returns>The new reserveOption.</returns>
    public static JsonObject ReserveOption(RuleEdit edit, JsonObject? existing)
    {
        ArgumentNullException.ThrowIfNull(edit);
        var o = existing?.DeepClone().AsObject() ?? new JsonObject { ["allowEndLack"] = true };
        o["enable"] = edit.Enable;
        o["avoidDuplicate"] = edit.AvoidDuplicate;

        // EPGStation refuses a period without avoidDuplicate. Without a new period, keep the rule's.
        if (!edit.AvoidDuplicate)
        {
            o.Remove("periodToAvoidDuplicate");
        }
        else if (edit.PeriodToAvoidDuplicate is int days)
        {
            o.Remove("periodToAvoidDuplicate");
            if (days > 0)
            {
                o["periodToAvoidDuplicate"] = days;
            }
        }

        return o;
    }
}
