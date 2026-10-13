using System;
using System.Collections.Generic;
using Jellyfin.Plugin.EpgStation.Configuration;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Common.Plugins;
using MediaBrowser.Model.Plugins;
using MediaBrowser.Model.Serialization;

namespace Jellyfin.Plugin.EpgStation;

/// <summary>
/// EPGStation recording control for Jellyfin: browse the guide, schedule and unschedule recordings.
/// </summary>
public class Plugin : BasePlugin<PluginConfiguration>, IHasWebPages
{
    /// <summary>
    /// Initializes a new instance of the <see cref="Plugin"/> class.
    /// </summary>
    /// <param name="applicationPaths">Application paths.</param>
    /// <param name="xmlSerializer">XML serializer.</param>
    public Plugin(IApplicationPaths applicationPaths, IXmlSerializer xmlSerializer)
        : base(applicationPaths, xmlSerializer)
    {
        Instance = this;
    }

    /// <inheritdoc />
    public override string Name => "EPGStation";

    /// <inheritdoc />
    public override string Description => "Schedule and unschedule EPGStation recordings from Jellyfin.";

    /// <inheritdoc />
    public override Guid Id => Guid.Parse("509fa560-d8d9-4761-9d70-0151f18660cf");

    /// <summary>
    /// Gets the current plugin instance.
    /// </summary>
    public static Plugin? Instance { get; private set; }

    /// <inheritdoc />
    public IEnumerable<PluginPageInfo> GetPages()
    {
        return
        [
            // Settings (dashboard → Plugins → EPGStation).
            new PluginPageInfo
            {
                Name = "EpgStationConfig",
                DisplayName = "EPGStation",
                EmbeddedResourcePath = GetType().Namespace + ".Configuration.configPage.html",
            },
        ];
    }
}
