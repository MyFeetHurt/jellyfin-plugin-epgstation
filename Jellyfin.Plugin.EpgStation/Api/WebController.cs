using System;
using System.Collections.Generic;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Jellyfin.Plugin.EpgStation.Api;

/// <summary>
/// Serves the user page at /EpgStation/Web/. Jellyfin lists plugin pages only for administrators,
/// so every user reaches the guide here; the page then calls the API with the user's own token.
/// </summary>
[ApiController]
[Route("EpgStation/Web")]
[AllowAnonymous]
public class WebController : ControllerBase
{
    private static readonly Dictionary<string, string> Files = new(StringComparer.Ordinal)
    {
        ["index.html"] = "text/html; charset=utf-8",
        ["app.js"] = "text/javascript; charset=utf-8",
        ["app.css"] = "text/css; charset=utf-8",
        ["icon.svg"] = "image/svg+xml",
    };

    /// <summary>
    /// Redirects /EpgStation/Web to /EpgStation/Web/ so relative URLs work behind any base URL.
    /// </summary>
    /// <returns>A redirect.</returns>
    [HttpGet("")]
    public ActionResult Root()
    {
        var path = Request.PathBase + Request.Path;
        return path.Value!.EndsWith('/') ? GetFile("index.html") : Redirect(path + "/");
    }

    /// <summary>
    /// One file of the page.
    /// </summary>
    /// <param name="file">File name.</param>
    /// <returns>The file.</returns>
    [HttpGet("{file}")]
    public ActionResult GetFile([FromRoute] string file)
    {
        if (!Files.TryGetValue(file, out var type))
        {
            return NotFound();
        }

        var stream = typeof(WebController).Assembly.GetManifestResourceStream(typeof(Plugin).Namespace + ".Web." + file);
        if (stream is null)
        {
            return NotFound();
        }

        Response.Headers.CacheControl = "no-cache";
        return File(stream, type);
    }
}
