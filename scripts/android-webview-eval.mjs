#!/usr/bin/env node
// CI 專用（2026-11-20，補助案 B2 提醒流程）：在 Android 模擬器裡的 App 網頁殼執行一段 JS、把結果印出來。
// 只給 scripts/android-reminder-smoke.sh 用，不會打包進 APK。
//
// 做法：debug 版 APK 的 WebView 開著遠端偵錯（Capacitor 對 debug 包預設開），
// smoke 腳本先用 `adb forward tcp:<port> localabstract:webview_devtools_remote_<pid>` 接上，
// 這支再用 Chrome DevTools Protocol 的 Runtime.evaluate 跑運算式（可以 await）。
//
// 用法：node scripts/android-webview-eval.mjs --port 9222 --expr "await MuneaNotify.permissionStatus()"
// 成功：stdout 印 JSON；運算式丟錯或逾時：exit 1。

const args = process.argv.slice(2);
function arg(name, fallback) {
  const index = args.indexOf(name);
  return index >= 0 && index + 1 < args.length ? args[index + 1] : fallback;
}

const port = Number(arg('--port', '9222'));
const expression = arg('--expr', '');
const timeoutMs = Number(arg('--timeout', '60')) * 1000;

if (!expression) {
  console.error('missing --expr');
  process.exit(2);
}

const timer = setTimeout(() => {
  console.error(`timeout after ${timeoutMs / 1000}s`);
  process.exit(1);
}, timeoutMs);

try {
  const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
  const page = targets.find((t) => t.type === 'page' && /localhost/.test(t.url || '')) || targets.find((t) => t.type === 'page');
  if (!page || !page.webSocketDebuggerUrl) throw new Error('no WebView page target: ' + JSON.stringify(targets).slice(0, 400));
  const socket = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', () => reject(new Error('websocket error')), { once: true });
  });
  const wrapped = `(async () => { ${/\breturn\b/.test(expression) ? expression : `return (${expression});`} })()`;
  socket.send(JSON.stringify({
    id: 1,
    method: 'Runtime.evaluate',
    params: { expression: wrapped, awaitPromise: true, returnByValue: true },
  }));
  const reply = await new Promise((resolve) => {
    socket.addEventListener('message', (event) => {
      const data = JSON.parse(event.data);
      if (data.id === 1) resolve(data);
    });
  });
  socket.close();
  clearTimeout(timer);
  if (reply.error || (reply.result && reply.result.exceptionDetails)) {
    console.error(JSON.stringify(reply.error || reply.result.exceptionDetails).slice(0, 2000));
    process.exit(1);
  }
  const value = reply.result && reply.result.result ? reply.result.result.value : undefined;
  console.log(JSON.stringify(value === undefined ? null : value));
  process.exit(0);
} catch (error) {
  clearTimeout(timer);
  console.error(String((error && error.stack) || error));
  process.exit(1);
}
