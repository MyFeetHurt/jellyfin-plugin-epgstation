using System;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Plugin.EpgStation.Configuration;

namespace Jellyfin.Plugin.EpgStation.EpgStation;

/// <summary>
/// Raw answer from EPGStation: status code, body and content type.
/// </summary>
/// <param name="Status">HTTP status (0 = EPGStation not reachable).</param>
/// <param name="Body">Response body.</param>
/// <param name="ContentType">Response content type.</param>
public sealed record EpgStationResponse(int Status, byte[] Body, string ContentType)
{
    /// <summary>
    /// Gets a value indicating whether the call succeeded (2xx).
    /// </summary>
    public bool Ok => Status is >= 200 and < 300;

    /// <summary>
    /// Gets the body as UTF-8 text.
    /// </summary>
    public string Text => Encoding.UTF8.GetString(Body);
}

/// <summary>
/// Thin HTTP client for the EPGStation 2.x REST API (http://host:8888/api/...).
/// </summary>
public class EpgStationClient
{
    private static readonly TimeSpan Timeout = TimeSpan.FromSeconds(30);
    private readonly IHttpClientFactory _httpClientFactory;

    /// <summary>
    /// Initializes a new instance of the <see cref="EpgStationClient"/> class.
    /// </summary>
    /// <param name="httpClientFactory">HTTP client factory.</param>
    public EpgStationClient(IHttpClientFactory httpClientFactory)
    {
        _httpClientFactory = httpClientFactory;
    }

    private static PluginConfiguration Config => Plugin.Instance?.Configuration ?? new PluginConfiguration();

    /// <summary>
    /// Gets a value indicating whether an EPGStation URL is configured.
    /// </summary>
    public static bool IsConfigured => Uri.TryCreate(Config.EpgStationUrl, UriKind.Absolute, out var u)
        && (u.Scheme == Uri.UriSchemeHttp || u.Scheme == Uri.UriSchemeHttps);

    /// <summary>
    /// Sends one request to EPGStation.
    /// </summary>
    /// <param name="method">HTTP method.</param>
    /// <param name="pathAndQuery">Path below /api/, e.g. "reserves?isHalfWidth=true".</param>
    /// <param name="jsonBody">Optional JSON body.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The response; status 0 when EPGStation could not be reached.</returns>
    public async Task<EpgStationResponse> SendAsync(HttpMethod method, string pathAndQuery, string? jsonBody, CancellationToken cancellationToken)
    {
        var config = Config;
        if (!IsConfigured)
        {
            return Error(0, "EPGStation URL is not configured.");
        }

        var url = new Uri(config.EpgStationUrl.TrimEnd('/') + "/api/" + pathAndQuery);
        using var request = new HttpRequestMessage(method, url);
        if (!string.IsNullOrEmpty(config.BasicAuthUser))
        {
            var token = Convert.ToBase64String(Encoding.UTF8.GetBytes(config.BasicAuthUser + ":" + config.BasicAuthPassword));
            request.Headers.Authorization = new AuthenticationHeaderValue("Basic", token);
        }

        if (jsonBody is not null)
        {
            request.Content = new StringContent(jsonBody, Encoding.UTF8, "application/json");
        }

        using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        cts.CancelAfter(Timeout);
        try
        {
            var http = _httpClientFactory.CreateClient();
            using var response = await http.SendAsync(request, cts.Token);
            var body = await response.Content.ReadAsByteArrayAsync(cts.Token);
            var type = response.Content.Headers.ContentType?.ToString() ?? "application/octet-stream";
            return new EpgStationResponse((int)response.StatusCode, body, type);
        }
        catch (HttpRequestException ex)
        {
            return Error(0, "EPGStation is not reachable: " + ex.Message);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return Error(0, "EPGStation did not answer in time.");
        }
    }

    /// <summary>
    /// GET helper.
    /// </summary>
    /// <param name="pathAndQuery">Path below /api/.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The response.</returns>
    public Task<EpgStationResponse> GetAsync(string pathAndQuery, CancellationToken cancellationToken)
        => SendAsync(HttpMethod.Get, pathAndQuery, null, cancellationToken);

    private static EpgStationResponse Error(int status, string message)
        => new(status, Encoding.UTF8.GetBytes(System.Text.Json.JsonSerializer.Serialize(new { message })), "application/json");
}
