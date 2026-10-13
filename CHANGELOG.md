# Changelog

## 0.1.1 (2026-10-13)

- Fix: the plugin did not load on Jellyfin 12.0 / 12.1 ("NotSupported") and 10.11.0–10.11.10: it was
  built against the newest Jellyfin libraries. It is now built against 12.0.0 and 10.11.0.

## 0.1.0 (2026-10-13)

First release.

- Guide (地デジ / BS / CS) with genre colours and channel logos; scheduled programmes are marked.
- Programme search by keyword (title, optionally description).
- Schedule a recording, cancel a reservation, stop a recording in progress, un-skip a rule's skipped airing.
- Reservation list (scheduled, conflicts, skipped) showing which Jellyfin user scheduled what.
- Settings: EPGStation URL (+ optional basic auth), which users may use it, encode mode for new reservations.
- English and Japanese, follows the browser language.
- Builds for Jellyfin 10.11 and 12.x.
