# Gyantra Architecture

> The authoritative architecture description now lives in the
> [README](README.md), which covers the system diagram, the ten-stage pipeline,
> the grounding model, the token-budget strategy, model routing, and the
> design trade-offs.
>
> This file is kept as a pointer so existing links do not break. The original
> pre-implementation draft is preserved at
> [`docs/architecture_original.md`](docs/architecture_original.md) for reference.

## Where to find what

| Topic | Location |
|-------|----------|
| System diagram and component map | [README → Architecture](README.md#architecture) |
| Stage-by-stage contracts | [README → The 10-stage pipeline](README.md#the-10-stage-pipeline) |
| Grounding and hallucination policy | [README → How grounding works](README.md#how-grounding-works) |
| Context-window handling | [README → Token-budget strategy](README.md#token-budget-strategy) |
| Provider routing and failover | [README → Model routing and failover](README.md#model-routing-and-failover) |
| API surface | [README → API reference](README.md#api-reference) |
| TKP schema | [README → Output contract](README.md#output-contract) |
| Trade-offs and known limits | [README → Design decisions](README.md#design-decisions-and-trade-offs) |

## Notable deviations from the original draft

The draft in `docs/architecture_original.md` was written before implementation.
Three things changed during the build:

1. **Frontend is React, not Streamlit.** The live progress experience — stage
   transitions, sub-stage progress, reviewing finished sections while later ones
   run — is central to the product, and Streamlit's rerun model works against
   all three.

2. **Stages 2–8 are split across two modules**
   (`stages_knowledge.py`, `stages_pedagogy.py`) rather than living inside the
   orchestrator. `pipeline.py` handles sequencing, progress and failure policy
   only.

3. **Validation is mostly deterministic.** The draft implied an LLM check per
   dimension. In the implementation three of four checks are pure code, and the
   grounding check runs a lexical pre-filter before asking a model to adjudicate
   only the shortlist — cheaper, faster and far more stable.
