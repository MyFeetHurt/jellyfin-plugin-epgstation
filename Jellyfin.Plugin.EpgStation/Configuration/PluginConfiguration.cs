using System;
using MediaBrowser.Model.Plugins;

namespace Jellyfin.Plugin.EpgStation.Configuration;

/// <summary>
/// Plugin settings, edited by administrators on the plugin's dashboard page.
/// </summary>
public class PluginConfiguration : BasePluginConfiguration
{
    /// <summary>
    /// Gets or sets the EPGStation base URL, e.g. http://192.168.0.10:8888.
    /// </summary>
    public string EpgStationUrl { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets the optional HTTP basic auth user name for EPGStation (reverse proxies).
    /// </summary>
    public string BasicAuthUser { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets the optional HTTP basic auth password for EPGStation.
    /// </summary>
    public string BasicAuthPassword { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets a value indicating whether every signed-in user may schedule and unschedule.
    /// When false, only administrators and the users in <see cref="AllowedUserIds"/> may.
    /// </summary>
    public bool AllowAllUsers { get; set; } = true;

    /// <summary>
    /// Gets or sets the users allowed when <see cref="AllowAllUsers"/> is false.
    /// </summary>
#pragma warning disable CA1819 // XML-serialized configuration needs an array.
    public Guid[] AllowedUserIds { get; set; } = [];
#pragma warning restore CA1819

    /// <summary>
    /// Gets or sets a value indicating whether allowed users (not only administrators) may create,
    /// change and delete EPGStation rules.
    /// </summary>
    public bool AllowRuleManagement { get; set; } = true;

    /// <summary>
    /// Gets or sets the EPGStation encode mode name added to new reservations ("" = none).
    /// </summary>
    public string EncodeMode { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets a value indicating whether the source TS is deleted after the encode.
    /// </summary>
    public bool DeleteOriginalAfterEncode { get; set; }
}
