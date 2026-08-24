# Model Business Impact & Serving Lifecycle

This layer turns offline recommendation experiments into an inspectable decision record without claiming causal production lift.

## Lifecycle

```text
Commerce interactions
      ↓
Temporal split
      ↓
Popularity / collaborative filtering / matrix factorization
      ↓
Ranking metrics + parameter search
      ↓
Business-impact scenario estimate
      ↓
Versioned JSON model artifact
      ↓
RecommendationService
      ↓
Latency + quality gates in CI/CT
```

## What is implemented

- Offline ranking metrics and model comparison
- Reproducible hyperparameter search
- Explicit business-impact estimator for conversion and revenue scenarios
- Versioned JSON persistence of matrix-factorization parameters and metadata
- Model reload with prediction equivalence checks
- Recommendation-serving boundary that returns model name, version, recommendations, and measured latency
- CI/CT thresholds that can block metric or latency regressions

## Important limitation

`incremental_revenue` is a scenario estimate derived from assumed conversion rates and average order value. It is **not** presented as causal lift. A production system would validate lift with an online controlled experiment and confidence intervals before making a business claim.

## Interview signal

The repository now demonstrates the chain:

**data → model → validation → tuning → versioning → serving → monitoring → business decision**

That is the core lifecycle expected from a Data Scientist who owns models beyond notebooks.
