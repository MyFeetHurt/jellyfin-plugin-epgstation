using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.EpgStation.EpgStation;

/// <summary>
/// Who scheduled a reservation through Jellyfin.
/// </summary>
/// <param name="UserName">Jellyfin user name.</param>
/// <param name="At">When it was scheduled (Unix ms).</param>
public sealed record ReservationOwner(string UserName, long At);

/// <summary>
/// Remembers which Jellyfin user created which EPGStation reservation (EPGStation has no users).
/// Kept as reservations.json in the plugin's data folder.
/// </summary>
public class ReservationLog : OwnerLog
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ReservationLog"/> class.
    /// </summary>
    /// <param name="logger">Logger.</param>
    public ReservationLog(ILogger<ReservationLog> logger)
        : base(logger, "reservations.json")
    {
    }
}

/// <summary>
/// Remembers which Jellyfin user created which EPGStation rule. Kept as rules.json.
/// </summary>
public class RuleLog : OwnerLog
{
    /// <summary>
    /// Initializes a new instance of the <see cref="RuleLog"/> class.
    /// </summary>
    /// <param name="logger">Logger.</param>
    public RuleLog(ILogger<RuleLog> logger)
        : base(logger, "rules.json")
    {
    }
}

/// <summary>
/// EPGStation id → Jellyfin user who created it, kept as a JSON file in the plugin's data folder.
/// </summary>
public abstract class OwnerLog
{
    private const int MaxEntries = 5000;
    private readonly object _lock = new();
    private readonly ILogger _logger;
    private readonly string _fileName;
    private Dictionary<long, ReservationOwner>? _entries;

    /// <summary>
    /// Initializes a new instance of the <see cref="OwnerLog"/> class.
    /// </summary>
    /// <param name="logger">Logger.</param>
    /// <param name="fileName">File name in the plugin's data folder.</param>
    protected OwnerLog(ILogger logger, string fileName)
    {
        _logger = logger;
        _fileName = fileName;
    }

    private string? FilePath => Plugin.Instance is null ? null : Path.Combine(Plugin.Instance.DataFolderPath, _fileName);

    /// <summary>
    /// Records the owner of a new reservation or rule.
    /// </summary>
    /// <param name="reserveId">EPGStation reserve or rule id.</param>
    /// <param name="userName">Jellyfin user name.</param>
    public void Add(long reserveId, string userName)
    {
        lock (_lock)
        {
            var entries = Load();
            entries[reserveId] = new ReservationOwner(userName, DateTimeOffset.UtcNow.ToUnixTimeMilliseconds());
            if (entries.Count > MaxEntries)
            {
                foreach (var old in entries.OrderBy(e => e.Value.At).Take(entries.Count - MaxEntries).ToList())
                {
                    entries.Remove(old.Key);
                }
            }

            Save(entries);
        }
    }

    /// <summary>
    /// Returns a copy of all known owners.
    /// </summary>
    /// <returns>Reserve id → owner.</returns>
    public Dictionary<long, ReservationOwner> Snapshot()
    {
        lock (_lock)
        {
            return new Dictionary<long, ReservationOwner>(Load());
        }
    }

    private Dictionary<long, ReservationOwner> Load()
    {
        if (_entries is not null)
        {
            return _entries;
        }

        _entries = [];
        var path = FilePath;
        try
        {
            if (path is not null && File.Exists(path))
            {
                _entries = JsonSerializer.Deserialize<Dictionary<long, ReservationOwner>>(File.ReadAllText(path)) ?? [];
            }
        }
        catch (Exception ex) when (ex is IOException or JsonException or UnauthorizedAccessException)
        {
            _logger.LogWarning(ex, "Could not read {Path}", path);
        }

        return _entries;
    }

    private void Save(Dictionary<long, ReservationOwner> entries)
    {
        var path = FilePath;
        if (path is null)
        {
            return;
        }

        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            var tmp = path + ".tmp";
            File.WriteAllText(tmp, JsonSerializer.Serialize(entries));
            File.Move(tmp, path, true);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            _logger.LogWarning(ex, "Could not write {Path}", path);
        }
    }
}
