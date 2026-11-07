# http-https-echo

The vendor uses integer image releases; 42 to 43 is the vendor's major-version track, not a conventional three-part semver patch. Read the tag's CHANGELOG.md and source comparison because the release note omits smaller runtime changes.

Release 43 moves Node 22 to 26 for the October security fixes. It also updates Express/Morgan, defaults missing/invalid response delays to zero, and stops publishing 32-bit ARM. The latter does not affect this amd64 cluster. Upstream #109 documents the old image's remotely reachable Brotli decoder issue.

onedr0p now runs a different echo app/chart. Treat his old mendhak image bumps as historical context, not target-version precedent.
