# Third-party notices

No third-party source code is vendored in this repository (rule R8).

| Project | License | Use | Status |
|---|---|---|---|
| DeepEval (confident-ai/deepeval) | Apache-2.0 | Optional `VerifierPort` adapter, pinned extra `deepeval` | Not yet installed (M3) |
| RAGAS (vibrantlabsai/ragas) | Apache-2.0 | Optional `GeneratorPort`/`VerifierPort` adapter, pinned extra `ragas` | Not yet installed (M2) |
| openai/evals | MIT | Ideas only (CompletionFn-style TargetPort, JSONL event vocabulary, closed-choice judges); no dependency, no copied code | Re-implemented |
| REA (morluto/rea) | MIT | Optional external tool for task F2; not a dependency | Not installed |

When an Apache-2.0 package is added as a dependency, retain its NOTICE text here and state any modifications.
