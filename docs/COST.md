# What VIPLAV costs, and how to keep it at zero extra

**Short answer: with the default settings, nothing beyond the Claude plan you already have.**

| Part | Default | Extra cost |
|---|---|---|
| Mind (Claude) | `VIPLAV_BRAIN=subscription`: your Claude plan, through Claude Code | **None.** It uses your plan's usage limits, the same as using Claude Code yourself |
| Ears | the browser's speech recognition, or local Whisper | **None** |
| Voice | the browser's voices, or local Kokoro / MMS | **None** |
| Running it | your own computer | **None** |
| Lambadi model training (later) | free GPU notebooks (Google Colab, Kaggle) | **None** |
| Publishing | public GitHub repository, with free Actions | **None** |

## The subscription brain

VIPLAV runs the official `claude` program (Claude Code) for each turn, signed in with your own plan. You set it up once:

1. Install Claude Code: https://code.claude.com
2. Run `claude` in a terminal and sign in with your Claude account.
3. Run `./run.sh`. No API key is needed.

**Is this allowed?** As of October 2026, Anthropic's [legal and compliance page](https://code.claude.com/docs/en/legal-and-compliance) says:

- a subscription sign-in is for "ordinary use of Claude Code"
- the policy does not prevent a user "signing in to the unmodified Claude Code binary with their own Claude subscription"
- plan limits "assume ordinary, individual usage of Claude Code and the Agent SDK"

VIPLAV for yourself fits that: it is the unmodified program, your own sign-in, for your own use. Two things don't fit, and VIPLAV must never do them:

- sharing one person's plan with other people
- running VIPLAV as a service for others on your plan

Each person who uses VIPLAV signs in with their own plan. Policies change, so check that page now and then.

**What "usage limits" means.** Plans allow a certain amount of use per time window. A long session uses more. If you reach the limit, VIPLAV says so plainly, and works again when the window resets. If your plan offers paid "extra usage" beyond the limits, leave it off, and you can never be charged more than the plan.

**Making your limits last longer:**

- `VIPLAV_EFFORT=low` or `medium` (the default). Higher effort thinks longer and uses more.
- `VIPLAV_SUBSCRIPTION_MODEL=sonnet`. Sonnet usually uses plan limits more slowly than Opus, and handles everyday conversation well. Leave it empty for your plan's default.
- `VIPLAV_WEB_SEARCH=false` when you don't need it. Searches add to each turn.
- **New chat** when you change subject entirely. A shorter conversation means less to re-read each turn. The board carries your threads over, so nothing is lost.

## The API brain (optional, pay per use)

`VIPLAV_BRAIN=api` uses an Anthropic API key instead, billed per use and separately from any plan. It's there for people without a plan. If you ever use it:

- set a monthly spend limit at console.anthropic.com
- know that model choice changes the price a lot. Per million input/output tokens: Opus 5.5 costs $4 / $20, Sonnet 5.5 $2 / $10, Haiku 5.5 $0.10 / $0.50.

## Before adding anything new

Ask: is there a free or local way? If the only way is paid, write down what it would cost and what the free alternative gives up, and let the owner decide.
