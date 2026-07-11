# Hosted MCP Revenue Pipeline — Design

date: 2026-07-11
status: approved (brainstorm complete; awaiting implementation plan)
predecessors: docs/demand-probe.md, docs/decision-gate.md,
docs/reviews/2026-07-06-leverage-backlog.md,
~/wiki/decisions/2026-04-15-simengine-gtm-options.md

## Goal

An automation pipeline that turns SimEngine's decision-intelligence niche into
recurring revenue with near-zero marginal labor: agents and agent builders
discover the hosted `decide_under_uncertainty` MCP service, self-serve onto a
free tier, upgrade through Stripe, and the product's own weekly forecast cycle
generates the marketing that brings the next user. Recurring human labor target:
**under 30 minutes/week** (approve one post draft, read one ops digest).

Decisions fixed during brainstorming:

- **Channel:** hosted MCP product (not consulting lead-gen, not a standalone
  forecast product).
- **Gate:** demand probe first; the paid build starts only on probe signal.
- **Infra budget:** ~$5–10/mo (one small VPS) + ~$12/yr domain.
- **Pricing:** free tier + flat monthly tiers. No metering, no overage.
- **Shape:** product funnel **plus** a self-marketing flywheel (approach B),
  chosen over funnel-only (A) and concierge-first (C) because the registry alone
  is an unproven traffic source and the flywheel is the only acquisition asset
  that compounds without labor.

## Phases and gates

Evidence gates between phases; nothing advances on enthusiasm.

### Phase 0 — Probe + free assets (now; ~1 session + 48h clock)

- Tony posts the demand probe (final text and channel list prepared from
  `docs/demand-probe.md`; posting itself stays human).
- Publish the open-source server to the MCP registry (manifest + runbook
  already prepared in `docs/PUBLISHING-MCP-REGISTRY.md`).
- Stand up a free landing page on GitHub Pages: positioning from
  `docs/server-card.md`, the FRED backtest
  (`docs/backtests/2026-07-06-fred-monthly-calibration.md`) as the trust
  anchor, and a waitlist email form.
- Zero spend; every artifact is valuable even if the probe fails.

### Phase 1 — Hosted funnel (gated on probe, per the existing decision rule)

- **10+ organic "I'd use this" in 48h** → full build: VPS, hosted MCP endpoint,
  instant key issuance, Stripe tiers.
- **3–9** → free hosted tier only (keys, caps, instrumentation); Stripe
  deferred until usage shows up.
- **≤2** → stop. Landing page and registry listing remain as credibility
  assets; effort returns to consulting (Phase C remains the live revenue
  channel).

### Phase 2 — Acquisition flywheel (once Phase 1 is live, even free-only)

Weekly automated cycle: resolve last week's forecasts → run new calibrated
forecasts on public data → republish the live track-record page → email Tony
one post draft + ops digest. Publishing is always human-approved.

### Kill criterion

If, 60 days after Phase 1 goes live, fewer than **~15 activated free keys**
(issued *and* used more than once) exist, the hosted bet is falsified: freeze
the funnel, keep the flywheel running as a consulting credibility engine.

## Architecture

### Open-core boundary

The public repo stays Apache-2.0 and zero-dep; nothing commercial is added to
`v3/`. All hosted-service code lives in a new **private repo `simengine-cloud`**
that imports the engine from a pinned checkout of the public repo (no vendoring,
no pip). This is the split LICENSE-COMMERCIAL.md already anticipates.

### Components (one VPS, Hetzner-class, ~€4.5/mo)

1. **`gateway.py`** — commercial front door. Stdlib HTTP service that:
   - terminates Bearer API-key auth;
   - enforces per-key monthly caps and meters usage;
   - exposes the MCP **Streamable HTTP** transport for
     `decide_under_uncertainty`, `simulate`, and `validate_config`
     (the existing `mcp_server.py` is stdio-only; this transport is the main
     new code);
   - calls the engine **in-process** (imports `kernel.py`/`validation.py`
     directly — no internal HTTP hop);
   - handles Stripe webhooks (`checkout.session.completed`,
     `customer.subscription.deleted`) to flip tiers.
   - Caddy in front for TLS + rate limiting (single binary; the one
     non-Python piece).

2. **`keys.sqlite`** — API keys, tier, usage counters, Stripe customer ID.
   Same sqlite pattern as the calibration ledger. Nightly `sqlite3 .backup`
   rsync'd to the home machine via cron (no cloud storage bill).

3. **Signup flow** — static page on the product domain: email in → free key
   emailed instantly and shown on-page. Upgrades via **Stripe Payment Links +
   customer portal** (no custom checkout). A daily reconcile cron cross-checks
   Stripe subscriptions against `keys.sqlite` so a missed webhook cannot
   strand a paying customer on the free tier.

4. **Email** — transactional free tier (Postmark/Brevo class, ≤100/day) for
   key delivery and the weekly digest. Fallback: key shown on-page only,
   email optional. No marketing-email machinery.

### Tiers (v1)

| Tier | Price | Cap |
|------|-------|-----|
| Free | $0 | 500 metered calls/mo |
| Pro | $29/mo | 10,000 metered calls/mo |

A "metered call" is one MCP tool invocation that reaches the engine
(`decide_under_uncertainty`, `simulate`); `validate_config` is free and
unmetered so agents can iterate on configs without burning quota.
Hard caps with a clear "upgrade" error payload agents can surface to their
humans. No metered billing, no overage charges. Pricing changes are always a
human decision.

### Security posture

The AST expression evaluator is the known multi-tenant risk (flagged in the
external reviews). Mitigations: every inbound config goes through the existing
`validate_config` + safe AST evaluator only; per-request timeout and
simulation-count ceiling; process memory limit; unprivileged service user.
**Launch is gated on a pass through the `security-and-hardening` skill
checklist.**

### Interfaces

- gateway → engine: read-only import of the pinned public repo.
- gateway → `keys.sqlite`: only writer.
- signup page → gateway `/keys` endpoint + Stripe.
- Nothing in the public repo references any of this.

## Flywheel (weekly cron, Sunday night, same VPS)

1. **Resolve** — fetch fresh FRED data (existing opt-in fetch path in
   `backtest.py`); resolve last cycle's open forecasts in the calibration
   ledger (`calibration.py`), exactly as the Predictions UI does by hand.
2. **Forecast** — run the engine on a fixed roster of public-data configs
   (start: UNRATE, CPIAUCSL, INDPRO — the three committed FRED series). The
   roster is a JSON list; adding a series is data, not code.
3. **Publish** — regenerate a static **track-record page** from the ledger:
   every forecast ever made, its resolution, rolling Brier/ECE, reliability
   curve. Deploy by committing to the landing-page repo (GitHub Pages rebuild
   is free; no metered Actions).
4. **Draft** — generate one short post draft, **template-based from the
   week's numbers (no LLM in the loop)**, and email it to Tony with the ops
   digest. Tony edits/posts or ignores; publishing never happens
   unattended.

**Positioning guardrail** (carried from `docs/decision-gate.md`): forecasts
are calibration evidence, never trade signals. Macro indicators only; no named
tradable contracts; the page states this explicitly.

## Ops and error handling

- **FRED unreachable** → skip the cycle, note it in the digest. The public
  page simply shows the previous state; degradation is invisible to visitors.
- **Gateway down** → free-tier external uptime ping (UptimeRobot class)
  emails Tony; systemd restart policy is the only auto-remediation.
- **Stripe webhook missed** → daily reconcile cron catches it (see above).
- **Weekly digest email** is the single ops surface: signups, active keys,
  calls served, Stripe events, forecast-cycle status, backup status.

## Testing

- `simengine-cloud` gets a `unittest` suite mirroring the public repo's
  style: auth, caps, metering, webhook handling, reconcile logic.
- A staging smoke script exercises the full path — signup → key → MCP call →
  cap-exceeded error → upgrade webhook — against a Stripe **test-mode**
  account before launch.
- The flywheel is testable offline against the committed FRED snapshots in
  `v3/backtest_data/`.

## Success metrics

- **Phase 0:** probe responses (10+ / 3–9 / ≤2 decision rule).
- **Phase 1:** activated free keys (used >1×); free→paid conversion. The
  first paying customer retires the "demand unproven" risk.
- **Phase 2:** track-record-page traffic → signup referrals.
- Kill criterion as above.

## What stays manual, by design

Posting the probe, approving flywheel posts, consulting delivery, pricing
changes. Everything else — key issuance, billing, caps, forecasting, page
updates, backups, alerts — runs unattended.

## Out of scope (YAGNI)

- Metered/usage-based billing and overage charges (revisit only with real
  usage data).
- OAuth on the hosted layer (deferred decision from 2026-06-02 stands;
  API keys only for v1).
- Marketing-email sequences, CRM, affiliate mechanics.
- Auto-posting to social channels (drafts only; human publishes).
- Multi-region, autoscaling, managed databases — one VPS until revenue argues
  otherwise.
- PyPI packaging (backlog #9; separate decision, unaffected here).
