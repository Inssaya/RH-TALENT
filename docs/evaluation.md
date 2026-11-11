# Evaluation of the ranking

## What is measured

`python -m app.cli eval` ranks the candidates of each job with the platform's scoring and compares with a keyword
baseline (BM25). Metrics: nDCG@10, precision@N (relevance 2 or 3), and the **counterfactual gap** (same CV with another
name; the absolute score difference divided by 100). It exits with status 1 unless the gain over BM25 is at least
`--min-gain` (default 0.05) and the maximum counterfactual gap is below 0.03. CI runs it on every push.

Current synthetic result (20 jobs x 15 candidates, seed 7): nDCG@10 0.97 against 0.82 for BM25, precision@5 0.96
against 0.70, counterfactual gap 0.

## Limits you must keep in mind

The default data is **synthetic**. Relevance grades are planted from each candidate's latent profile (not produced by the
scoring function, so the test is not circular), but synthetic CVs are cleaner and more regular than real ones, and
the generator draws vocabulary from the same taxonomy the scorer uses. Results therefore show **non-regression and the
absence of identity effects**, not real accuracy. A claim about real performance needs a human-annotated set.

## Commands

```bash
python -m app.cli synth --out synth.json --jobs 20 --per-job 15 --seed 7   # generate a dataset
python -m app.cli eval                                                       # generate and evaluate in one go
python -m app.cli eval --data synth.json --n 5 --min-gain 0.05               # evaluate a file
```

## Dataset format (JSON)

```json
{
  "jobs": [
    {
      "title": "Data Scientist",
      "description": "…at least a few sentences…",
      "city": "Casablanca", "country": "Maroc", "remote": "hybrid", "contract_type": "permanent",
      "min_years_experience": 3, "education_level": 7,
      "languages": [{"code": "fr", "level": "B2"}],
      "skills_required": ["Python", "Machine learning", "SQL"], "skills_nice": ["Docker"],
      "requirements": [{"id": "q0", "text": "Hands-on experience with Python", "type": "requirement"}],
      "knockouts": [], "lang": "fr",
      "candidates": [
        {"id": "c1", "name": "Lina Benali", "text": "full CV text…", "grade": 3, "lang": "fr"}
      ]
    }
  ]
}
```

`grade` is the relevance: 0 not relevant, 1 weak, 2 good, 3 excellent. Keys starting with `_` and the keys
`occupation` and `candidates` are not part of the job template. The candidate `name` must appear in `text`: the bench
replaces it to compute the counterfactual gap on grade-3 candidates.

## Plugging a human-annotated set

1. Collect real jobs and CVs with consent (the specification plans 10 jobs x 50 CVs, 30 real and 20 written by people).
2. Have two annotators, one a professional recruiter, grade every CV for every job from 0 to 3 using a written guide;
   compute their agreement (weighted kappa) and keep it as the human ceiling.
3. Write the set in the format above (CV text can come from the parser: `app.ai.parsing.parse_document`).
4. Split by job: roughly half for development (calibration), half frozen for the final measurement. Never calibrate on the test half.
5. `python -m app.cli eval --data human-test.json`. Report nDCG@10 and precision@N with bootstrap confidence intervals
   (not computed by the bench yet) and compare with BM25.

The annotation tool of the specification (F-DAT-03) is not built; any spreadsheet that ends in this JSON works.

## Calibrating for a new embeddings provider

The semantic sub-score maps the cosine between job and profile embeddings from [`SEM_LOW`, `SEM_HIGH`] to [0, 1].
The specification sets them at the 5th and 95th percentiles of the cosine on the development set. There is no tool for
this yet: compute the cosines of the development pairs with `app.ai.embeddings.embed` and `cosine`, then set the two
variables. Also re-run `eval`, and re-check the score weights (grid search, keep new weights only if nDCG@10 improves by
0.02 or more and the counterfactual gap stays under 0.03).

## Real LLM mode

With `MISTRAL_API_KEY` set, requirement assessment and extraction use the LLM; the formula and the evidence check do not
change. CI runs without an API key, so `eval` exercises the rule-based path for requirements; **the LLM mode has no benchmark
yet**. Run `eval` with the key set (and a small dataset, since every candidate costs LLM calls) before trusting it.
