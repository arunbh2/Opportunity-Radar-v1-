# Opportunity Radar

A lightweight intelligence tracker for Australian development funding and
procurement, built for Practical Action Asia. It watches DFAT-related sources
weekly, scores new items against your geographies (Nepal, Bangladesh, India,
Southeast Asia / Indo-Pacific) and themes (climate resilience, DRR, EWS,
energy access, water security, GEDSI, livelihoods, agriculture, risk finance),
and produces a markdown digest with pre-positioning suggestions — likely
primes, partners to call, capability notes to prepare.

## What it watches

Automated: AusTender, GrantConnect, DFAT business notifications and the
Development Procurement Pipeline, embassy DAP pages (India, Nepal,
Bangladesh), ACIAR, and the news pages of ASI, Palladium, DT Global, Abt and
Tetra Tech (early signals before RFPs drop).

Semi-manual (printed as a weekly checklist in every digest): AusConnect
(login-walled), Devex funding search, ACFID circulars.

## Quick start (run it yourself, today)

```bash
pip install -r requirements.txt
python radar.py
```

The first run **baselines** each source silently — it records everything
currently on each page so that the *second* run onward shows only genuinely
new items. Run it twice a few days apart and the digest comes alive.

Digests land in `digests/YYYY-MM-DD.md` (and `digests/latest.md`).
State lives in `data/seen.json` — delete it to reset, or run
`python radar.py --rescan` to score everything regardless of history.

## Automate it with GitHub Actions (free)

1. Create a **private** GitHub repository and push this folder to it.
2. That's it. The workflow in `.github/workflows/radar.yml` runs every
   Monday 08:30 IST, commits the digest, and opens it as a GitHub issue
   so it lands in your notifications/email.
3. To run on demand: repo → Actions → Opportunity Radar → "Run workflow".
4. Optional: create a label called `radar` in the repo so issues are tagged.

## The weekly discipline (15 minutes)

1. Open Monday's digest issue. Scan HIGH items first.
2. Work the **manual checklist** (AusConnect login especially).
3. For each HIGH item, do the "Do now" action — or consciously decide not to.
4. Tune as you learn: every false positive → add an `exclude` term;
   every miss → add a keyword or source in `config.yaml`. Ten minutes of
   tuning per week compounds fast.

## Tuning guide

Everything lives in `config.yaml`:

- **keywords** — geography terms score 3, themes 2, boosters (RFT/EOI/grant
  language) 3. `min_score: 2` means a single theme hit on a DFAT source
  qualifies; raise it if the digest gets noisy.
- **sources** — add any public page as a new `type: html` entry. Add more
  AusTender keyword-search URLs by duplicating that entry with a different
  `Keyword=` parameter. Pages behind logins go in as `type: manual`.
- **playbook** — this is where the strategy lives. Each entry maps trigger
  terms to likely actors and pre-positioning actions. Update it whenever you
  learn who's bidding on what.

## Known limitations (by design, for the MVP)

- Scoring is on **link/title text only** — it doesn't open each opportunity
  page. Titles on AusTender/GrantConnect are usually descriptive enough; the
  digest link takes you to the detail.
- Source pages occasionally block bots (DFAT's pipeline page sometimes 403s).
  When a fetch fails, the source automatically appears in the manual
  checklist instead of failing silently.
- Government sites change their HTML. If a source goes quiet for several
  weeks, open it manually and check whether the URL moved; update
  `config.yaml`.
- First run per source shows nothing new (baselining) — this is correct
  behaviour, not a bug.

## Improvement roadmap (when the discipline sticks)

1. **Page-level enrichment** — fetch each HIGH item's detail page and pull
   closing date, value, and agency into the digest table.
2. **AusTender OCDS API** — pull *awarded* contract notices monthly to track
   who is actually winning (competitor intelligence, not just opportunities).
3. **Email delivery** — add an SMTP step to the workflow, or simply rely on
   GitHub issue notifications (which already email you).
4. **Claude summarisation layer** — pipe each HIGH item's detail page through
   the Anthropic API for a 3-line assessment and a sharper recommended
   action. The deterministic playbook stays as the floor.
5. **Shared triage** — once it works for you, GitHub issues give the team
   comment threads, assignees and a natural go/no-go record per opportunity.
