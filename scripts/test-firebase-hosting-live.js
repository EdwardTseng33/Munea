const assert = require("node:assert/strict");

const baseUrl = (process.env.FIREBASE_HOSTING_TEST_URL || "http://127.0.0.1:5000").replace(/\/$/, "");

async function request(pathname, options = {}) {
  return fetch(`${baseUrl}${pathname}`, {
    redirect: "manual",
    ...options,
  });
}

async function main() {
  for (const pathname of ["/", "/en", "/ja", "/es", "/privacy", "/terms", "/support"]) {
    const response = await request(pathname);
    assert.equal(response.status, 200, `${pathname} must return 200`);
    assert.match(response.headers.get("content-type") || "", /text\/html/i);
  }

  // 帶尾斜線的寫法會被轉到不帶的那個 —— 確認轉址是對的、不是壞掉
  for (const dir of ["en", "ja", "es"]) {
    const response = await request(`/${dir}/`);
    assert.equal(response.status, 301, `/${dir}/ must redirect to the canonical path`);
    assert.equal(response.headers.get("location"), `/${dir}`);
  }

  // 每個語系真的送出該語系的頁（不是四個網址指到同一份中文）
  for (const [pathname, lang] of [
    ["/", "zh-Hant-TW"],
    ["/en", "en"],
    ["/ja", "ja"],
    ["/es", "es"],
  ]) {
    const html = await (await request(pathname)).text();
    assert.match(html, new RegExp(`<html\\s+lang="${lang}"`), `${pathname} must serve lang=${lang}`);
  }

  // 版型與文案表住在 app-site 外面（site-src/），結構上就送不出去。
  // 萬一哪天有人搬回來，這幾條會立刻紅燈。
  for (const pathname of [
    "/_src/index.html",
    "/_src/i18n/zh.json",
    "/_src/config.json",
    "/site-src/index.html",
  ]) {
    const response = await request(pathname);
    assert.equal(response.status, 404, `${pathname} must not be published`);
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
