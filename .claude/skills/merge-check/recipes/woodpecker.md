# woodpecker

## Both image pins override appVersion

The HelmRelease explicitly sets `server.image.tag` and `agent.image.tag`. A chart appVersion increase does not update either app while those overrides remain. Read both child charts and compare effective rendered image references, not metadata labels.

On #898 chart 3.7.5 to 3.7.6 changed appVersion 3.19.0 to 3.20.1, but both effective images stayed v3.19.0. The only local render changes were appVersion-derived metadata. That chart-only bump does not deliver the new application's security fixes.

## Future app upgrade

Read both app releases 3.20.0 and 3.20.1. The former warns about an unintended envsubst breaking change; the latter restores the old implementation. An intentional app upgrade should move server and agent together and separately inspect the PostgreSQL database, Kubernetes pipeline backend and environment-substitution behavior. Do not infer that those checks ran from a chart-only review.
