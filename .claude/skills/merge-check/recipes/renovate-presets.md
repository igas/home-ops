# renovate-presets

Review the exact imported preset, not every change in the preset repository. This repo imports `apps/talosFactory.json5` directly. Fetch it at both pinned tags, compare its contents, and follow any nested extends.

On #882, 8.1.0 and 10.0.1 supplied byte-identical talosFactory presets with no nested extends. The intervening major notes concerned tooling and other presets. cluster-template#2334 and #2326 reported missing baseConfig/cnpg presets, neither imported here.

On #932, 10.0.1 to 11.0.0 adds only `separateMinorPatch: true` for `custom.talos-factory`, with no nested extends. This keeps patch proposals available alongside the next minor; it does not enforce upgrade order or enable automerge. Check later local package rules for overrides. The release's breaking oxfmt change affects preset-repository tooling, not consumers of this file. [Upstream #154](https://github.com/home-operations/renovate-presets/pull/154) explains the behavior; [onedr0p #12057](https://github.com/onedr0p/home-ops/pull/12057) merged the exact version with only preset-pin changes.

This dependency runs in hosted Renovate. A cluster HelmRelease, appVersion, chart values/schema and node version are not applicable checks; state that explicitly rather than inventing a workload.
