# Prototype Instructions

Run the local server yourself and open the preview in the in-app browser. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Durable product preference: recommendation and monitoring logic should prioritize domestic emerging brands, new stores, new brands, first stores, new consumer brands, new Chinese brands, and early expansion signals over routine mature-chain store-opening news. Internet search sources should use keyword coverage such as "新店", "新品牌", "首店", "国货", and "新锐消费品牌" to broaden discovery.

Durable source expansion preference: current-stage source expansion should prioritize high-quality industry media, commercial real-estate/first-store media, precise Google News RSS, and tightly scoped internet searches. Lower-quality broad social/public feeds should stay disabled or deferred until a later project phase with stronger import, cleaning, deduplication, and verification workflows.

Daily report requirement: daily招商日报 should summarize the previous day's important leasing news with dense, prioritized blocks. Each block must be traceable to a hotspot detail and original source link. AI workflow should keep fact curation, report writing, and accuracy verification as separate agents; verification should reject or downgrade claims that cannot be traced to collected evidence.

Daily report date policy: when the app labels a report as yesterday's briefing, candidates with parseable publish dates outside the coverage date must be excluded. Candidates with unparseable dates may be retained only as supplemental leads tagged "日期待核验", and the report must surface that risk.

Durable delivery requirement: published and packaged handoffs should keep a small, useful demo dataset such as `data/hotspots.db` or exported demo JSON, while excluding dependency folders, local environment files, design artifacts, caches, and other development intermediates from the handoff package.

Durable Windows handoff requirement: local ZIP packages should include the built `dist` frontend so Windows recipients can launch with Python 3.9+ only in the normal path. `start-windows.bat` should skip Node.js when `dist/index.html` exists and write a `startup-log.txt` when startup fails.
