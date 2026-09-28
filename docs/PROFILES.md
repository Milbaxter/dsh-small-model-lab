# Released harness configurations

The comparison uses the npm-locked DSH CLI 0.1.7-rc.2 with the Python SDK
0.1.5rc1 transport client. `--modern` selects this runtime explicitly; the
original P0 fixture remains reproducible with the SDK's bundled native runtime.

- `sdk-minimal`: the released minimal SDK composition, with its persistent bash tool.
- `standard`: the released web standard agent preset, mounted onto the SDK host.
- `standard+autonomy-policy`: the same standard composition plus the exact policy
  vendored from optimal-deepseek-harness-setup at
  `02c392bb074fbc8600e7f42386f1105258e267be`.

The SDK does not select an agent preset itself. The lab bridge selects standard
when each agent is created, and the run trace must contain the durable
`agent-preset/selected` event. Host tool rows are disabled using the released web
patch, and the standard preset supplies the tools. The web host's subagent model
selection service is included without enabling model switching.

Both standard arms have the same small-context adaptation: compaction headroom
1,024 tokens, threshold ratio 0.75, retention 2,048 tokens, summary maximum 1,024
tokens. The upstream 65,536-token headroom is incompatible with this experiment's
16,384-token context. These are **adapted standard baselines**, not unmodified
upstream defaults. Model routing and sampling are identical between arms.
Session compression is disabled to retain directly inspectable JSONL traces.

The scripted integration test actually launches each released composition,
executes bash, checks the resulting file, checks preset-selection traces,
verifies identical tool catalogs between the two standard arms, and confirms
that the autonomy policy appears only in the candidate's model prompt.
It establishes configuration validity; it does not establish benchmark gains.
