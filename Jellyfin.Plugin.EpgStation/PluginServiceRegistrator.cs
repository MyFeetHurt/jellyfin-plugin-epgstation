using Jellyfin.Plugin.EpgStation.EpgStation;
using MediaBrowser.Controller;
using MediaBrowser.Controller.Plugins;
using Microsoft.Extensions.DependencyInjection;

namespace Jellyfin.Plugin.EpgStation;

/// <summary>
/// Registers the plugin's services with Jellyfin's DI container.
/// </summary>
public class PluginServiceRegistrator : IPluginServiceRegistrator
{
    /// <inheritdoc />
    public void RegisterServices(IServiceCollection serviceCollection, IServerApplicationHost applicationHost)
    {
        serviceCollection.AddSingleton<EpgStationClient>();
        serviceCollection.AddSingleton<ReservationLog>();
    }
}
