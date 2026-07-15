const assert = require("node:assert/strict");

const baseUrl = (process.env.FIREBASE_HOSTING_TEST_URL || "http://127.0.0.1:5000").replace(/\/$/, "");

async function request(pathname, options = {}) {
  return fetch(`${baseUrl}${pathname}`, {
    redirect: "manual",
    ...options,
  });
}

async function main() {
  for (const pathname of ["/", "/privacy", "/terms", "/support"]) {
    const response = await request(pathname);
    assert.equal(response.status, 200, `${pathname} must return 200`);
    assert.match(response.headers.get("content-type") || "", /text\/html/i);
  }

  for (const pathname of ["privacy", "terms", "support"]) {
    const response = await request(`/${pathname}.html`);
    assert.equal(response.status, 301, `/${pathname}.html must permanently redirect`);
    assert.equal(response.headers.get("location"), `/${pathname}`);
  }

  const verification = await request("/googleaa0c51d3d9781eb5.html");
  assert.equal(verification.status, 200);
  assert.equal(
    (await verification.text()).trim(),
    "google-site-verification: googleaa0c51d3d9781eb5.html",
  );

  const missing = await request("/this-page-must-not-exist-munea");
  assert.equal(missing.status, 404, "Unknown paths must not become false 200 responses");

  console.log("[ok] Firebase Hosting routes passed");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
