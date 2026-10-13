# Changelog

## 0.2.0 (2026-10-13)

- Rules (EPGStation's automatic recordings): new **Rules** tab to list, create, change, turn on/off
  and delete them. The editor covers keyword, exclude words, title or full text, broadcast types or
  channels, genres, weekdays and time, free only, skip already recorded; other rule settings (save
  folder, encode, regex, durations...) are kept as they are. **Preview** shows what a rule would
  record before saving. Each rule shows who created it in Jellyfin.
- **Record series** in a programme's details: a rule prefilled with the show name and channel.
- Search: **Make a rule from this search**.
- Reservations made by a rule have an **Edit rule** button.
- Setting: whether users (not only administrators) may manage rules (default: yes).

## 0.1.2 (2026-10-13)

- Fix: "Open the guide" and the guide link on the settings page showed Jellyfin's "Page not found".
  They now open the guide in a new tab.

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
