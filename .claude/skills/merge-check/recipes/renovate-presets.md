# renovate-presets

Review the exact imported preset, not every change in the preset repository. This repo imports `apps/talosFactory.json5` directly. Fetch it at both pinned tags, compare its contents, and follow any nested extends.

On #882, 8.1.0 and 10.0.1 supplied byte-identical talosFactory presets with no nested extends. The intervening major notes concerned tooling and other presets. cluster-template#2334 and #2326 reported missing baseConfig/cnpg presets, neither imported here.

This dependency runs in hosted Renovate. A cluster HelmRelease, appVersion, chart values/schema and node version are not applicable checks; state that explicitly rather than inventing a workload.
