# Leader-elected controllers (openebs localpv-provisioner and similar)

Risk: a new version whose readiness probe needs leadership deadlocks a rollout, because the new pod cannot become ready while the old pod holds the lease. Caught on PR #675 (openebs).

## Preflight: standby pod

1. Clone the Deployment's pod template into a bare `Pod`, `restartPolicy: Never`, **fresh labels**. Copying the template labels lets the ReplicaSet adopt the pod and kill the real one.
2. Swap the image to the new tag. Apply in the component's namespace.
3. It sits as lease standby. `kubectl wait --for=condition=Ready pod/<name> --timeout=120s`. Ready while standby means the rollout will not deadlock.
4. `kubectl exec` a `wget -qO- localhost:<port>/<probe path>` for each probe path to see the responses.
5. Confirm the Lease holder is unchanged: `kubectl get lease -n <ns>`.
6. Delete the pod.
