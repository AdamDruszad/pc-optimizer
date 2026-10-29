# Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by
[SignPath Foundation](https://signpath.org/).

> **Status:** the application to the SignPath Foundation open source program is in progress.
> Releases up to and including 3.0.1 are **not** signed.

## What is signed

Only binaries built from this repository's source by the GitHub Actions `release` workflow
(`.github/workflows/release.yml`) on a version tag:

- `GameBooster.exe` (the application, built with PyInstaller)
- `GameBooster-Setup-x.y.z.exe` (the installer, built with Inno Setup)

Third-party binaries bundled with the application (the Python runtime, Tcl/Tk, psutil) are
included as published by their maintainers and are not re-signed by this project. Every signing
request is approved manually.

## Team roles

| Role | Members |
|---|---|
| Committers and reviewers | [AdamDruszad](https://github.com/AdamDruszad) |
| Approvers | [AdamDruszad](https://github.com/AdamDruszad) |

Changes from contributors outside this team are reviewed by a committer before merging. All team
members use multi-factor authentication on GitHub and SignPath.

## Privacy policy

This program will not transfer any information to other networked systems unless specifically
requested by the user or the person installing or operating it.

GameBooster has no telemetry and no update check. It contacts the network only when you ask it to:
the latency test opens a TCP connection to the host you enter, and the DNS page changes the DNS
servers of the adapter you select. All data (change journal, settings, log) stays on your computer
in `%LOCALAPPDATA%\GameBooster`.

## System changes

GameBooster changes Windows settings (power plan, services, registry values, startup entries, DNS).
Every change is listed in a confirmation dialog before it is applied, its original value is stored,
and it can be reverted from the **History** page. The installer registers an uninstaller in
**Settings → Apps**.
