using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Net.Http;
using System.Net.Mime;
using System.Security.Claims;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Jellyfin.Plugin.EpgStation.EpgStation;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.EpgStation.Api;

/// <summary>
/// Search request from the web page.
/// </summary>
public class SearchRequest
{
    /// <summary>Gets or sets the keyword.</summary>
    public string Keyword { get; set; } = string.Empty;

    /// <summary>Gets or sets a value indicating whether the description is searched too.</summary>
    public bool Description { get; set; }

    /// <summary>Gets or sets the broadcast types to search (GR, BS, CS, SKY); empty = all.</summary>
#pragma warning disable CA1819, CA2227
    public string[] Types { get; set; } = [];
#pragma warning restore CA1819, CA2227
}

/// <summary>
/// Reservation request from the web page.
/// </summary>
public class ReserveRequest
{
    /// <summary>Gets or sets the EPGStation program id.</summary>
    public long ProgramId { get; set; }
}

/// <summary>
/// The plugin's REST API (below /EpgStation) and the user page (/EpgStation/Web/).
/// Every API call needs a signed-in Jellyfin user allowed by the plugin settings; the calls are
/// forwarded to a fixed list of EPGStation endpoints, never to arbitrary URLs.
/// </summary>
[ApiController]
[Route("EpgStation")]
public class EpgStationController : ControllerBase
{
    private static readonly string[] BroadcastTypes = ["GR", "BS", "CS", "SKY"];
    private readonly EpgStationClient _client;
    private readonly ReservationLog _log;
    private readonly ILogger<EpgStationController> _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="EpgStationController"/> class.
    /// </summary>
    /// <param name="client">EPGStation client.</param>
    /// <param name="log">Reservation owner log.</param>
    /// <param name="logger">Logger.</param>
    public EpgStationController(EpgStationClient client, ReservationLog log, ILogger<EpgStationController> logger)
    {
        _client = client;
        _log = log;
        _logger = logger;
    }

    private string UserName => User.FindFirstValue(ClaimTypes.Name) ?? string.Empty;

    private bool IsAdmin => User.IsInRole("Administrator");

    private bool IsAllowed
    {
        get
        {
            var config = Plugin.Instance?.Configuration;
            if (config is null)
            {
                return false;
            }

            if (config.AllowAllUsers || IsAdmin)
            {
                return true;
            }

            return Guid.TryParse(User.FindFirstValue("Jellyfin-UserId"), out var id) && config.AllowedUserIds.Contains(id);
        }
    }

    /// <summary>
    /// Plugin and EPGStation status for the current user.
    /// </summary>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Status JSON.</returns>
    [HttpGet("Status")]
    [Authorize]
    [Produces(MediaTypeNames.Application.Json)]
    public async Task<ActionResult> GetStatus(CancellationToken cancellationToken)
    {
        var status = new JsonObject
        {
            ["userName"] = UserName,
            ["isAdmin"] = IsAdmin,
            ["allowed"] = IsAllowed,
            ["configured"] = EpgStationClient.IsConfigured,
            ["pluginVersion"] = Plugin.Instance?.Version.ToString(),
        };
        if (IsAllowed && EpgStationClient.IsConfigured)
        {
            var version = await _client.GetAsync("version", cancellationToken);
            status["connected"] = version.Ok;
            status["epgstation"] = version.Ok ? JsonNode.Parse(version.Text) : null;
            if (!version.Ok)
            {
                status["error"] = ErrorText(version);
            }
        }

        return Content(status.ToJsonString(), MediaTypeNames.Application.Json);
    }

    /// <summary>
    /// Channel list.
    /// </summary>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>EPGStation channel items.</returns>
    [HttpGet("Channels")]
    [Authorize]
    public Task<ActionResult> GetChannels(CancellationToken cancellationToken)
        => Forward(HttpMethod.Get, "channels", null, cancellationToken);

    /// <summary>
    /// Channel logo. Anonymous because &lt;img&gt; cannot send the Jellyfin token; it only exposes logos.
    /// </summary>
    /// <param name="channelId">EPGStation channel id.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The logo image.</returns>
    [HttpGet("Channels/{channelId}/Logo")]
    [AllowAnonymous]
    public async Task<ActionResult> GetLogo([FromRoute] long channelId, CancellationToken cancellationToken)
    {
        var res = await _client.GetAsync("channels/" + channelId.ToString(CultureInfo.InvariantCulture) + "/logo", cancellationToken);
        if (!res.Ok || !res.ContentType.StartsWith("image/", StringComparison.OrdinalIgnoreCase))
        {
            return NotFound();
        }

        Response.Headers.CacheControl = "public, max-age=86400";
        return File(res.Body, res.ContentType);
    }

    /// <summary>
    /// Guide data of one broadcast type.
    /// </summary>
    /// <param name="type">GR, BS, CS or SKY.</param>
    /// <param name="startAt">Start (Unix ms).</param>
    /// <param name="endAt">End (Unix ms).</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>EPGStation schedules (channel + programs).</returns>
    [HttpGet("Schedules")]
    [Authorize]
    public Task<ActionResult> GetSchedules([FromQuery] string type, [FromQuery] long startAt, [FromQuery] long endAt, CancellationToken cancellationToken)
    {
        if (!BroadcastTypes.Contains(type) || endAt <= startAt || endAt - startAt > TimeSpan.FromDays(2).TotalMilliseconds)
        {
            return Task.FromResult<ActionResult>(BadRequest());
        }

        var flags = string.Concat(BroadcastTypes.Select(t => "&" + t + "=" + (t == type ? "true" : "false")));
        return Forward(HttpMethod.Get, Inv($"schedules?startAt={startAt}&endAt={endAt}&isHalfWidth=true{flags}"), null, cancellationToken);
    }

    /// <summary>
    /// One programme.
    /// </summary>
    /// <param name="programId">EPGStation program id.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The programme.</returns>
    [HttpGet("Programs/{programId}")]
    [Authorize]
    public Task<ActionResult> GetProgram([FromRoute] long programId, CancellationToken cancellationToken)
        => Forward(HttpMethod.Get, Inv($"schedules/detail/{programId}?isHalfWidth=true"), null, cancellationToken);

    /// <summary>
    /// Keyword search in the guide.
    /// </summary>
    /// <param name="request">Search request.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Matching programmes.</returns>
    [HttpPost("Search")]
    [Authorize]
    public Task<ActionResult> Search([FromBody] SearchRequest request, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        var keyword = request.Keyword.Trim();
        if (keyword.Length == 0 || keyword.Length > 200)
        {
            return Task.FromResult<ActionResult>(BadRequest());
        }

        var types = request.Types.Length == 0 ? BroadcastTypes : request.Types.Where(BroadcastTypes.Contains).ToArray();
        var option = new JsonObject
        {
            ["keyword"] = keyword,
            ["name"] = true,
            ["description"] = request.Description,
            ["extended"] = request.Description,
        };
        foreach (var t in BroadcastTypes)
        {
            option[t] = types.Contains(t);
        }

        var body = new JsonObject { ["option"] = option, ["isHalfWidth"] = true, ["limit"] = 300 };
        return Forward(HttpMethod.Post, "schedules/search", body.ToJsonString(), cancellationToken);
    }

    /// <summary>
    /// Reservations (all: normal, conflicts, skipped, overlaps).
    /// </summary>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>EPGStation reserves.</returns>
    [HttpGet("Reserves")]
    [Authorize]
    public async Task<ActionResult> GetReserves(CancellationToken cancellationToken)
    {
        if (!IsAllowed)
        {
            return StatusCode(StatusCodes.Status403Forbidden);
        }

        // EPGStation pages reservations (limit/offset): fetch every page, so no reservation loses
        // its mark in the guide.
        const int Page = 500;
        var all = new JsonArray();
        for (var offset = 0; ; offset += Page)
        {
            var res = await _client.GetAsync(Inv($"reserves?type=all&isHalfWidth=true&offset={offset}&limit={Page}"), cancellationToken);
            if (!res.Ok)
            {
                return ToResult(res);
            }

            var page = JsonNode.Parse(res.Text);
            var items = page?["reserves"]?.AsArray() ?? [];
            var count = items.Count;
            foreach (var item in items.ToList())
            {
                items.Remove(item); // a node can only have one parent
                all.Add(item);
            }

            var total = page?["total"]?.GetValue<int>() ?? 0;
            if (count < Page || all.Count >= total)
            {
                return Content(new JsonObject { ["reserves"] = all, ["total"] = all.Count }.ToJsonString(), MediaTypeNames.Application.Json);
            }
        }
    }

    /// <summary>
    /// Reserve id lists by state in a time range, used to mark the guide.
    /// </summary>
    /// <param name="startAt">Start (Unix ms).</param>
    /// <param name="endAt">End (Unix ms).</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>EPGStation reserve lists.</returns>
    [HttpGet("ReserveLists")]
    [Authorize]
    public Task<ActionResult> GetReserveLists([FromQuery] long startAt, [FromQuery] long endAt, CancellationToken cancellationToken)
        => Forward(HttpMethod.Get, Inv($"reserves/lists?startAt={startAt}&endAt={endAt}"), null, cancellationToken);

    /// <summary>
    /// Recordings in progress.
    /// </summary>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>EPGStation recording items.</returns>
    [HttpGet("Recording")]
    [Authorize]
    public Task<ActionResult> GetRecording(CancellationToken cancellationToken)
        => Forward(HttpMethod.Get, "recording?isHalfWidth=true&limit=100", null, cancellationToken);

    /// <summary>
    /// Which Jellyfin user scheduled which reservation.
    /// </summary>
    /// <returns>Reserve id → owner.</returns>
    [HttpGet("Owners")]
    [Authorize]
    public ActionResult GetOwners()
    {
        if (!IsAllowed)
        {
            return StatusCode(StatusCodes.Status403Forbidden);
        }

        var owners = _log.Snapshot().ToDictionary(e => e.Key.ToString(CultureInfo.InvariantCulture), e => e.Value);
        return Content(JsonSerializer.Serialize(owners), MediaTypeNames.Application.Json);
    }

    /// <summary>
    /// Schedules a recording of one programme.
    /// </summary>
    /// <param name="request">The programme.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>{reserveId}.</returns>
    [HttpPost("Reserves")]
    [Authorize]
    public async Task<ActionResult> AddReserve([FromBody] ReserveRequest request, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (!IsAllowed)
        {
            return StatusCode(StatusCodes.Status403Forbidden);
        }

        if (request.ProgramId <= 0)
        {
            return BadRequest();
        }

        var config = Plugin.Instance!.Configuration;
        var body = new JsonObject { ["programId"] = request.ProgramId, ["allowEndLack"] = true };
        if (!string.IsNullOrEmpty(config.EncodeMode))
        {
            body["encodeOption"] = new JsonObject
            {
                ["mode1"] = config.EncodeMode,
                ["isDeleteOriginalAfterEncode"] = config.DeleteOriginalAfterEncode,
            };
        }

        var res = await _client.SendAsync(HttpMethod.Post, "reserves", body.ToJsonString(), cancellationToken);
        if (res.Ok)
        {
            try
            {
                var id = JsonNode.Parse(res.Text)?["reserveId"]?.GetValue<long>();
                if (id is long reserveId)
                {
                    _log.Add(reserveId, UserName);
                }
            }
            catch (JsonException)
            {
                // The reservation exists; only the owner note is lost.
            }

            _logger.LogInformation("{User} scheduled EPGStation program {ProgramId}", UserName, request.ProgramId);
        }

        return ToResult(res);
    }

    /// <summary>
    /// Unschedules a reservation. EPGStation turns this into a skip for rule reservations and
    /// stops (keeping the file) when the programme is already recording.
    /// </summary>
    /// <param name="reserveId">EPGStation reserve id.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Empty on success.</returns>
    [HttpDelete("Reserves/{reserveId}")]
    [Authorize]
    public async Task<ActionResult> DeleteReserve([FromRoute] long reserveId, CancellationToken cancellationToken)
    {
        var result = await Forward(HttpMethod.Delete, Inv($"reserves/{reserveId}"), null, cancellationToken);
        if (result is ContentResult { StatusCode: 200 })
        {
            _logger.LogInformation("{User} unscheduled EPGStation reserve {ReserveId}", UserName, reserveId);
        }

        return result;
    }

    /// <summary>
    /// Un-skips a skipped rule reservation (records it again).
    /// </summary>
    /// <param name="reserveId">EPGStation reserve id.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Empty on success.</returns>
    [HttpDelete("Reserves/{reserveId}/Skip")]
    [Authorize]
    public async Task<ActionResult> UnskipReserve([FromRoute] long reserveId, CancellationToken cancellationToken)
    {
        var result = await Forward(HttpMethod.Delete, Inv($"reserves/{reserveId}/skip"), null, cancellationToken);
        if (result is ContentResult { StatusCode: 200 })
        {
            _logger.LogInformation("{User} un-skipped EPGStation reserve {ReserveId}", UserName, reserveId);
        }

        return result;
    }

    /// <summary>
    /// EPGStation encode modes (for the settings page).
    /// </summary>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>EPGStation config.</returns>
    [HttpGet("Config")]
    [Authorize(Policy = "RequiresElevation")]
    public async Task<ActionResult> GetEpgStationConfig(CancellationToken cancellationToken)
    {
        var res = await _client.GetAsync("config", cancellationToken);
        if (!res.Ok)
        {
            return ToResult(res);
        }

        var encode = JsonNode.Parse(res.Text)?["encode"] ?? new JsonArray();
        return Content(new JsonObject { ["encode"] = encode.DeepClone() }.ToJsonString(), MediaTypeNames.Application.Json);
    }

    private static string Inv(FormattableString s) => s.ToString(CultureInfo.InvariantCulture);

    private static string ErrorText(EpgStationResponse res)
    {
        try
        {
            var node = JsonNode.Parse(res.Text);
            var errors = node?["errors"]?.ToString();
            var message = node?["message"]?.ToString();
            return !string.IsNullOrEmpty(errors) ? errors : message ?? res.Text;
        }
        catch (JsonException)
        {
            return res.Status == 0 ? res.Text : $"HTTP {res.Status}";
        }
    }

    private ContentResult ToResult(EpgStationResponse res)
    {
        if (res.Ok)
        {
            var text = res.Body.Length == 0 ? "{}" : res.Text;
            return new ContentResult { StatusCode = 200, Content = text, ContentType = MediaTypeNames.Application.Json };
        }

        // EPGStation reports errors as HTTP 500 with the reason in "errors"; pass it on as 502.
        var error = new JsonObject { ["status"] = res.Status, ["error"] = ErrorText(res) };
        return new ContentResult { StatusCode = StatusCodes.Status502BadGateway, Content = error.ToJsonString(), ContentType = MediaTypeNames.Application.Json };
    }

    private async Task<ActionResult> Forward(HttpMethod method, string path, string? body, CancellationToken cancellationToken)
    {
        if (!IsAllowed)
        {
            return StatusCode(StatusCodes.Status403Forbidden);
        }

        return ToResult(await _client.SendAsync(method, path, body, cancellationToken));
    }
}
