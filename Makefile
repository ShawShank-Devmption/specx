# SpecX — one-day build. Every target is idempotent. Run from repo root.
SHELL := /bin/bash
.DEFAULT_GOAL := help
PY := cd python && uv run
export SPECX_ROOT := $(CURDIR)

help: ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-22s\033[0m %s\n",$$1,$$2}'

setup: ## install everything (node deps + playwright chromium + python venv)
	cd platform && npm install && npx playwright install chromium
	cd python && uv sync --all-extras
	cd dashboard && [ -f package.json ] && npm install || true

check-contracts: ## validate fixtures/ and results/ against contracts/*.schema.json
	uv run --with jsonschema python scripts/check_contracts.py

lint: ## lint + typecheck both sides
	cd platform && npm run lint && npm run typecheck
	$(PY) ruff check . && $(PY) ruff format --check .

test: check-contracts ## unit tests that need no sandbox and no LLM
	cd platform && npm test
	$(PY) pytest -q -m "not sandbox and not llm"

test-integration: ## tests that need the sandbox running (make sandbox first)
	$(PY) pytest -q -m "sandbox and not llm"

# ---- runtime -------------------------------------------------------------
apps: ## start both seed apps (foreground; use two terminals or `make apps &`)
	cd platform && npm run apps

sandbox: ## start the sandbox HTTP server on :4000 (expects apps running)
	cd platform && npm run sandbox

# ---- pipeline stages (each writes results/<stage>/…) ---------------------
generate: ## F3: results/tools/<app>.tools.json + results/contracts/<app>.contracts.json
	cd platform && npm run cli -- generate --app shop && npm run cli -- generate --app admin

generate-free: ## F3 without model calls: deterministic template names (apps must be running)
	cd platform && ANTHROPIC_API_KEY= npm run cli -- generate --app shop --namer template && ANTHROPIC_API_KEY= npm run cli -- generate --app admin --namer template

test-free-integration: ## real browser + Python integration tests, no paid API calls (apps/sandbox/tools required)
	cd platform && ANTHROPIC_API_KEY= npm run test:integration
	cd python && ANTHROPIC_API_KEY= uv run pytest -q -m "sandbox and not llm"

verify: ## F1: results/verdicts/f1.jsonl, tools get status verified|quarantined (make s6 later fills verdict.anomaly)
	cd platform && npm run cli -- verify --app shop && npm run cli -- verify --app admin

graph: ## results/graphs/<app>.graph.json (rerun after s1 and evaluate; keeps S2 gnn edges)
	cd platform && npm run cli -- graph --app shop && npm run cli -- graph --app admin

platform-demo: generate verify graph ## Dev A stages only (apps must be running)

versions: ## record node/playwright/chromium versions → results/final/platform_versions.json
	cd platform && npm run cli -- versions

s6: ## train + evaluate anomaly layer → results/s6/metrics.json; also scores results/verdicts/f1.jsonl (anomaly field)
	$(PY) python -m specx.safety.s6.run --apps shop,admin --out results/s6

s1: ## PPO vs random vs coverage fuzzers → results/s1/metrics.json + results/verdicts/s1*.jsonl
	$(PY) python -m specx.safety.s1.run --apps shop,admin --steps 1500 --seeds 3 --out results/s1

quarantine: ## fold S1/S6 violations into tool status (run after s1)
	cd platform && npm run cli -- quarantine --app shop && npm run cli -- quarantine --app admin

s2: ## GNN vs rule-based vs MLP → results/s2/metrics.json + gnn edges merged into graphs
	$(PY) python -m specx.safety.s2.run --graphs results/graphs --verdicts results/verdicts --out results/s2

baseline: ## F4 raw_dom + generated conditions → results/trials/raw_dom.jsonl, generated.jsonl
	$(PY) python -m specx.evalx.run --conditions raw_dom,generated --apps shop,admin --trials 5

optimise: ## F2 loop (text baseline) + S4 arms → results/patches/, results/trials/gate_*.jsonl, results/f2/metrics.json
	$(PY) python -m specx.optim.loop --apps shop,admin --arms text_trace,text_structured,multimodal_structured --max-iters 4

evaluate: ## F4 verified + optimised conditions → results/trials/verified.jsonl, optimised.jsonl
	$(PY) python -m specx.evalx.run --conditions verified,optimised --apps shop,admin --trials 5

report: ## stats + results/final/REPORT.md + results/final/numbers.json (dashboard reads this)
	$(PY) python -m specx.stats.report --results results --out results/final

demo: generate verify s6 s1 quarantine graph s2 baseline optimise evaluate report ## full pipeline (apps + sandbox must be running)

dashboard: ## serve the React dashboard on :5173
	cd dashboard && npm run dev

clean-results: ## wipe results/ except final/
	find results -mindepth 1 -maxdepth 1 ! -name final ! -name .gitkeep -exec rm -rf {} +
