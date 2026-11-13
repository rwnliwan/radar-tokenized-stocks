// N1 (fix ronde review DeepSeek Radar): the Exit Score band thresholds
// (40/70) are duplicated in dashboard/risk.py:112 and
// web/src/lib/risk.ts:81. This test loads the SHARED fixture
// qa/exit_score_bands_fixture.json and checks the web implementation
// against EVERY case in it. The dashboard worker runs the same fixture
// against dashboard/risk.py exit_score_band.
//
// Usage: node qa/test_exit_score_bands.mjs  (exit 0 = PASS)
// Requires Node >= 22.18 (type stripping imports risk.ts directly).
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { exitScoreBand } from "../web/src/lib/risk.ts";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const fixture = JSON.parse(
  readFileSync(join(ROOT, "qa", "exit_score_bands_fixture.json"), "utf8"),
);

const FAILURES = [];
function check(name, ok, detail = "") {
  console.log((ok ? "PASS " : "FAIL ") + name + (detail ? ` — ${detail}` : ""));
  if (!ok) FAILURES.push(name);
}

// The fixture must carry exactly the six boundary cases the task
// names; a silently shrunk fixture is a blind guard, not a pass.
const EXPECTED = [
  { score: 0, band: "low" },
  { score: 39, band: "low" },
  { score: 40, band: "medium" },
  { score: 69, band: "medium" },
  { score: 70, band: "high" },
  { score: 100, band: "high" },
];
check(
  "fixture has all 6 boundary cases",
  Array.isArray(fixture.cases) &&
    fixture.cases.length === EXPECTED.length &&
    EXPECTED.every((e) =>
      fixture.cases.some((c) => c.score === e.score && c.band === e.band),
    ),
  `cases=${JSON.stringify(fixture.cases)}`,
);

// Every fixture case against the web implementation.
for (const { score, band } of fixture.cases) {
  const got = exitScoreBand(score);
  check(`exitScoreBand(${score}) === ${band}`, got === band, `got ${got}`);
}

// The fixture's declared ranges must agree with its own cases.
for (const [band, [lo, hi]] of Object.entries(fixture.bands ?? {})) {
  const inRange = fixture.cases
    .filter((c) => c.band === band)
    .every((c) => c.score >= lo && c.score <= hi);
  check(`fixture range ${band} [${lo},${hi}] covers its cases`, inRange);
}

if (FAILURES.length) {
  console.error(`\n${FAILURES.length} FAILURE(S): ${FAILURES.join(", ")}`);
  process.exit(1);
}
console.log(`\nAll ${fixture.cases.length} fixture cases PASS (web/src/lib/risk.ts exitScoreBand).`);
