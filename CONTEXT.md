# home-ops

A Talos, Kubernetes and Flux GitOps cluster for home operations. Dependency updates arrive as Renovate pull requests; this glossary covers the vocabulary of deciding whether one is safe to merge.

## Language

### Merge review

**Verdict**:
The outcome of a merge check on one PR: `safe`, `safe with prep`, or `hold`. An unverified PR is `hold`, never `safe`.
_Avoid_: result, status, approval

**Prep**:
The action the operator takes before or right after merging a `safe with prep` PR.
_Avoid_: follow-up, TODO

**Preflight**:
A read-only runtime check against the live cluster that tests one named risk, limited to creating and deleting one throwaway Pod.
_Avoid_: dry-run, smoke test, canary

**Recipe**:
A per-component review or preflight procedure stored beside the merge-check skill. A risk with no recipe is a recipe gap.
_Avoid_: runbook, playbook

**Precedent**:
Evidence from onedr0p's home-ops that the same version is merged and has stayed unreverted.
_Avoid_: upstream, reference

**Layer order**:
The sequence merge checks run in: node, platform, operators, apps. Lower layers first, because their changes reach everything above.
_Avoid_: priority, dependency order

### Dependency updates

**Bump**:
A Renovate pull request changing one dependency, or one Renovate group, from one version to another.
_Avoid_: update PR, dependency PR
