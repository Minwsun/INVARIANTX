import assert from "node:assert/strict";
import test from "node:test";

import { normalizeApiBase } from "./api-base.mjs";

test("normalizes Render hostnames", () => {
  assert.equal(
    normalizeApiBase("invariantx-api.onrender.com"),
    "https://invariantx-api.onrender.com",
  );
  assert.equal(
    normalizeApiBase("invariantx-api"),
    "https://invariantx-api.onrender.com",
  );
  assert.equal(normalizeApiBase("https://api.example.com"), "https://api.example.com");
  assert.equal(normalizeApiBase(), "http://localhost:8000");
});
