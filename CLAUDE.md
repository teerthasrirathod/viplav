# Working on VIPLAV

## Principle 1: low cost, always

The owner pays for nothing beyond the Claude plan they already have. Every change keeps it that way:

- **The brain uses the owner's Claude plan by default** (`VIPLAV_BRAIN=subscription`), through the official, unmodified `claude` program, signed in by the owner. Never make a paid API key required. The API brain stays an option, not the default.
- **Ears and voice are free.** Use the browser's built-in speech or open-source local models. Never add a paid speech service, or any paid service, without asking first.
- **Testing spends nothing.** Test against fakes (`tests/` has fake Claude streams and a fake `claude` program). Run the real model only when it's truly needed, keep those runs to a few short turns at low effort, and say when you did.
- **Hosting, CI and training stay on free tiers:** local machine, GitHub's free Actions for public repositories, and free GPU notebooks (Colab, Kaggle) for model training.
- **Cheap must not mean stuck.** If something can only be done with a paid service, say what it would cost and offer the closest free alternative. Don't silently drop the feature.

## Other principles

- **Languages are first-class:** English, Hindi, Telugu, Lambadi, and mixing them. Each language is written in its own script (see `viplav/languages.py`).
- **Be honest about what's tested.** Say which parts ran against the real model and which against fakes.
- **Keep it simple:** plain Python and plain browser JavaScript, with no build step.

## Commands

```bash
pip install -e ".[dev]" && python -m pytest -q     # tests (no keys, no cost)
for f in web/*.js; do node --check "$f"; done      # JS syntax
./run.sh                                           # run locally
```
