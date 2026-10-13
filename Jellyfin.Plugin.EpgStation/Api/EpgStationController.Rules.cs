using System;
using System.Globalization;
using System.Linq;
using System.Net.Http;
using System.Net.Mime;
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
/// EPGStation rules (automatic recordings). Only for administrators and, when the setting
/// "users may manage rules" is on, the users allowed to record. The page sends only the fields
/// its editor shows (<see cref="RuleEdit"/>); everything else on a rule (save folder, encode,
/// regex, durations...) is kept, and new rules get the plugin's encode setting.
/// </summary>
public partial class EpgStationController
{
    private bool CanManageRules => IsAdmin || (IsAllowed && (Plugin.Instance?.Configuration.AllowRuleManagement ?? false));

    /// <summary>
    /// All rules.
    /// </summary>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>EPGStation rules.</returns>
    [HttpGet("Rules")]
    [Authorize]
    public async Task<ActionResult> GetRules(CancellationToken cancellationToken)
    {
        if (!CanManageRules)
        {
            return StatusCode(StatusCodes.Status403Forbidden);
        }

        return await GetAllPages("rules?type=all", "rules", cancellationToken);
    }

    /// <summary>
    /// One rule.
    /// </summary>
    /// <param name="ruleId">EPGStation rule id.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The rule.</returns>
    [HttpGet("Rules/{ruleId}")]
    [Authorize]
    public async Task<ActionResult> GetRule([FromRoute] long ruleId, CancellationToken cancellationToken)
    {
        if (!CanManageRules)
        {
            return StatusCode(StatusCodes.Status403Forbidden);
        }

        return ToResult(await _client.GetAsync(Inv($"rules/{ruleId}"), cancellationToken));
    }

    /// <summary>
    /// Which Jellyfin user created which rule.
    /// </summary>
    /// <returns>Rule id → owner.</returns>
    [HttpGet("RuleOwners")]
    [Authorize]
    public ActionResult GetRuleOwners()
    {
        if (!CanManageRules)
        {
            return StatusCode(StatusCodes.Status403Forbidden);
        }

        var owners = _ruleLog.Snapshot().ToDictionary(e => e.Key.ToString(CultureInfo.InvariantCulture), e => e.Value);
        return Content(JsonSerializer.Serialize(owners), MediaTypeNames.Application.Json);
    }

    /// <summary>
    /// Programmes a rule would record (EPGStation's search with the rule's conditions).
    /// </summary>
    /// <param name="edit">The rule as edited.</param>
    /// <param name="ruleId">The rule being edited, if any: its kept conditions (regex, durations...) apply too.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Matching programmes.</returns>
    [HttpPost("RulePreview")]
    [Authorize]
    public async Task<ActionResult> PreviewRule([FromBody] RuleEdit edit, [FromQuery] long? ruleId, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(edit);
        if (!CanManageRules)
        {
            return StatusCode(StatusCodes.Status403Forbidden);
        }

        if (RuleBuilder.Validate(edit) is string error)
        {
            return RuleError(error);
        }

        // Same merge as UpdateRule, so the preview shows what the saved rule will record.
        JsonObject? existing = null;
        if (ruleId is long id)
        {
            var current = await _client.GetAsync(Inv($"rules/{id}"), cancellationToken);
            if (!current.Ok)
            {
                return ToResult(current);
            }

            existing = JsonNode.Parse(current.Text)?["searchOption"] as JsonObject;
        }

        var option = RuleBuilder.SearchOption(edit, existing);
        option.Remove("searchPeriods"); // a rule's own search window, not a schedules/search option
        var body = new JsonObject { ["option"] = option, ["isHalfWidth"] = true, ["limit"] = 300 };
        return ToResult(await _client.SendAsync(HttpMethod.Post, "schedules/search", body.ToJsonString(), cancellationToken));
    }

    /// <summary>
    /// Creates a rule.
    /// </summary>
    /// <param name="edit">The rule.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>{ruleId}.</returns>
    [HttpPost("Rules")]
    [Authorize]
    public async Task<ActionResult> AddRule([FromBody] RuleEdit edit, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(edit);
        if (!CanManageRules)
        {
            return StatusCode(StatusCodes.Status403Forbidden);
        }

        if (RuleBuilder.Validate(edit) is string error)
        {
            return RuleError(error);
        }

        var rule = new JsonObject
        {
            ["isTimeSpecification"] = false,
            ["searchOption"] = RuleBuilder.SearchOption(edit, null),
            ["reserveOption"] = RuleBuilder.ReserveOption(edit, null),
        };
        var config = Plugin.Instance!.Configuration;
        if (!string.IsNullOrEmpty(config.EncodeMode))
        {
            rule["encodeOption"] = new JsonObject
            {
                ["mode1"] = config.EncodeMode,
                ["isDeleteOriginalAfterEncode"] = config.DeleteOriginalAfterEncode,
            };
        }

        var res = await _client.SendAsync(HttpMethod.Post, "rules", rule.ToJsonString(), cancellationToken);
        if (res.Ok)
        {
            try
            {
                if (JsonNode.Parse(res.Text)?["ruleId"]?.GetValue<long>() is long ruleId)
                {
                    _ruleLog.Add(ruleId, UserName);
                    _logger.LogInformation("{User} added EPGStation rule {RuleId} ({Keyword})", UserName, ruleId, edit.Keyword);
                }
            }
            catch (JsonException)
            {
                // The rule exists; only the owner note is lost.
            }
        }

        return ToResult(res);
    }

    /// <summary>
    /// Changes a rule: the editor's fields replace the rule's, everything else is kept.
    /// </summary>
    /// <param name="ruleId">EPGStation rule id.</param>
    /// <param name="edit">The rule as edited.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Empty on success.</returns>
    [HttpPut("Rules/{ruleId}")]
    [Authorize]
    public async Task<ActionResult> UpdateRule([FromRoute] long ruleId, [FromBody] RuleEdit edit, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(edit);
        if (!CanManageRules)
        {
            return StatusCode(StatusCodes.Status403Forbidden);
        }

        if (RuleBuilder.Validate(edit) is string error)
        {
            return RuleError(error);
        }

        var current = await _client.GetAsync(Inv($"rules/{ruleId}"), cancellationToken);
        if (!current.Ok)
        {
            return ToResult(current);
        }

        var old = JsonNode.Parse(current.Text)?.AsObject();
        if (old is null)
        {
            return RuleError("RuleInvalid");
        }

        // Time-specified rules (a channel + clock time, no search) are edited in EPGStation only.
        if (old["isTimeSpecification"]?.GetValue<bool>() == true)
        {
            return RuleError("RuleIsTimeSpecified");
        }

        var rule = new JsonObject
        {
            ["isTimeSpecification"] = false,
            ["searchOption"] = RuleBuilder.SearchOption(edit, old["searchOption"] as JsonObject),
            ["reserveOption"] = RuleBuilder.ReserveOption(edit, old["reserveOption"] as JsonObject),
        };
        foreach (var keep in new[] { "saveOption", "encodeOption" })
        {
            if (old[keep] is JsonNode node)
            {
                rule[keep] = node.DeepClone();
            }
        }

        var res = await _client.SendAsync(HttpMethod.Put, Inv($"rules/{ruleId}"), rule.ToJsonString(), cancellationToken);
        if (res.Ok)
        {
            _logger.LogInformation("{User} changed EPGStation rule {RuleId}", UserName, ruleId);
        }

        return ToResult(res);
    }

    /// <summary>
    /// Enables a rule.
    /// </summary>
    /// <param name="ruleId">EPGStation rule id.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Empty on success.</returns>
    [HttpPut("Rules/{ruleId}/Enable")]
    [Authorize]
    public Task<ActionResult> EnableRule([FromRoute] long ruleId, CancellationToken cancellationToken)
        => RuleAction(HttpMethod.Put, ruleId, "/enable", "enabled", cancellationToken);

    /// <summary>
    /// Disables a rule (its future reservations go away; the rule stays).
    /// </summary>
    /// <param name="ruleId">EPGStation rule id.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Empty on success.</returns>
    [HttpPut("Rules/{ruleId}/Disable")]
    [Authorize]
    public Task<ActionResult> DisableRule([FromRoute] long ruleId, CancellationToken cancellationToken)
        => RuleAction(HttpMethod.Put, ruleId, "/disable", "disabled", cancellationToken);

    /// <summary>
    /// Deletes a rule and its reservations; finished recordings stay.
    /// </summary>
    /// <param name="ruleId">EPGStation rule id.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Empty on success.</returns>
    [HttpDelete("Rules/{ruleId}")]
    [Authorize]
    public Task<ActionResult> DeleteRule([FromRoute] long ruleId, CancellationToken cancellationToken)
        => RuleAction(HttpMethod.Delete, ruleId, string.Empty, "deleted", cancellationToken);

    private async Task<ActionResult> RuleAction(HttpMethod method, long ruleId, string suffix, string verb, CancellationToken cancellationToken)
    {
        if (!CanManageRules)
        {
            return StatusCode(StatusCodes.Status403Forbidden);
        }

        var res = await _client.SendAsync(method, Inv($"rules/{ruleId}{suffix}"), null, cancellationToken);
        if (res.Ok)
        {
            _logger.LogInformation("{User} {Verb} EPGStation rule {RuleId}", UserName, verb, ruleId);
        }

        return ToResult(res);
    }

    private ContentResult RuleError(string code)
        => new()
        {
            StatusCode = StatusCodes.Status400BadRequest,
            Content = new JsonObject { ["error"] = code }.ToJsonString(),
            ContentType = MediaTypeNames.Application.Json,
        };
}
