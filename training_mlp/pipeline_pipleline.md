flowchart TD
    A[Load CSV] --> B[Temporal split]
    B --> C[CV pool 90%]
    B --> D[Gap 80 bars discarded]
    B --> E[Test set last 10% frozen]
    C --> F[Naive baseline majority class]
    F --> G{Walk-forward CV 5 folds}
    G --> H[Purge + embargo split]
    H --> I[StandardScaler fit on train only]
    I --> J{Epoch loop max 100}
    J --> K[Train epoch AdamW + warmup cosine]
    K --> L[Evaluate val loss]
    L -->|patience < 15| J
    L -->|patience = 15| M[Early stop restore best weights]
    M --> N[Save model_fold_N.pt + scaler_fold_N.pkl]
    N -->|next fold| G
    G -->|all folds done| O[Select best fold by val AUC]
    O --> P[Save model_best.pt + scaler_best.pkl]
    P --> Q[evaluate.py]
    Q --> R[Load X_test.npy + model_best.pt + scaler_best.pkl]
    R --> S[Single pass on frozen test set]
    S --> T[Save results_test.json + W&B log]