"""Guard every FlashHead lane against visual drift.

2026-07-20 的教訓：為了對齊 B2B 展示間，有人把 a05/a06 的條件圖換成壓扁裁切，
但 App 的貼合數字（web/src/styles.css .fh-overlay）沒跟著改，正式線的臉就歪了——
而當時的把關只看「展示間 + 後端」，完全沒看 App，所以一路綠燈放行。

這支現在守四件事：
1. 正式線（a05/a06）的條件圖 = App 立繪的原生正方形裁切，貼在 App CSS 寫死的那個 y。
2. App 自己的貼合數字（styles.css / app.js）跟後端宣告的正式線約定逐字對得上。
3. 兩支臉引擎的約定表一模一樣——備援機接手時臉不能換個樣子。
4. 展示間（a05d/a06d）走自己的實驗格，而且 B2B 頁不准直接叫正式線的角色代號。
"""

from __future__ import annotations

import ast
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
CANVAS = (1080, 1920)
MAX_MEAN_ABSOLUTE_ERROR = 5.0

ENGINES = {
    "modal": ROOT / "deploy" / "modal-avatar" / "flashhead_modal_dev.py",
    "runpod": ROOT / "deploy" / "runpod-avatar" / "flashhead_server.py",
    "sync-tool": ROOT / "deploy" / "runpod-avatar" / "sync-face-assets.py",
}
ASSETS = ROOT / "deploy" / "modal-avatar" / "assets"
CONDITION_IMAGE = {
    "a05": ASSETS / "a05-prod-square-640.png",
    "a06": ASSETS / "a06-prod-square-640.png",
    "a05d": ASSETS / "a05-demo-fill-512.png",
    "a06d": ASSETS / "a06-demo-fill-512.png",
}
# 角色代號 → App 立繪檔名（展示間的實驗格切自同一張正式立繪）。
BACKGROUND_OF = {"a05": "a05", "a06": "a06", "a05d": "a05", "a06d": "a06"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def literal_namespace(path: Path) -> dict:
    """把 .py 檔最上層「純資料」的賦值挖出來——不 import，免得拖進 torch/modal。"""
    namespace: dict = {}
    module = ast.parse(path.read_text(encoding="utf-8"))
    for node in module.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            namespace[target.id] = _eval(node.value, namespace)
        except ValueError:
            continue  # 有 os.environ.get 之類的就跳過，不是這支要守的東西
    return namespace


def _eval(node: ast.AST, namespace: dict):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in namespace:
            return namespace[node.id]
        raise ValueError(node.id)
    if isinstance(node, ast.Dict):
        return {_eval(k, namespace): _eval(v, namespace) for k, v in zip(node.keys, node.values)}
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval(item, namespace) for item in node.elts]
    raise ValueError(type(node).__name__)


def engine_contracts() -> dict:
    tables = {}
    for name, path in ENGINES.items():
        namespace = literal_namespace(path)
        table = namespace.get("AVATAR_RENDER_CONTRACTS")
        if not table:
            raise AssertionError(f"{name}: AVATAR_RENDER_CONTRACTS 讀不到（{path}）")
        tables[name] = table

    reference_name, reference = next(iter(tables.items()))
    for name, table in tables.items():
        if table != reference:
            raise AssertionError(
                f"臉引擎的貼合約定漂掉了：{name} 跟 {reference_name} 不一致"
                "——備援機接手時臉會換個樣子"
            )
    print(f"engines agree on render contract: {', '.join(tables)}")
    return reference


def check_condition_images(contracts: dict) -> None:
    for char, contract in sorted(contracts.items()):
        crop = contract["source_crop"]
        model = contract["model_input"]
        bg_name = BACKGROUND_OF[char]
        app_bg = ROOT / "web" / "flashhead" / f"bg-{bg_name}.png"
        b2b_bg = ROOT / "munea-b2b" / "flashhead" / f"bg-{bg_name}.png"
        if sha256(app_bg) != sha256(b2b_bg):
            raise AssertionError(f"{bg_name}: App 跟 B2B 的立繪底圖不同步了")

        box = (crop["x"], crop["y"], crop["x"] + crop["width"], crop["y"] + crop["height"])
        with Image.open(app_bg).convert("RGB") as source:
            if source.size != CANVAS:
                raise AssertionError(f"{bg_name}: 立繪應為 {CANVAS}，實際 {source.size}")
            expected = source.crop(box).resize((model["width"], model["height"]), Image.Resampling.LANCZOS)
        path = CONDITION_IMAGE[char]
        with Image.open(path).convert("RGB") as actual:
            if actual.size != (model["width"], model["height"]):
                raise AssertionError(
                    f"{char}: 條件圖應為 {model['width']}x{model['height']}，實際 {actual.size}"
                )
            error = float(
                np.abs(np.asarray(expected, dtype=np.int16) - np.asarray(actual, dtype=np.int16)).mean()
            )
        if error > MAX_MEAN_ABSOLUTE_ERROR:
            raise AssertionError(
                f"{char}: 條件圖跟宣告的裁切對不上（MAE={error:.3f}，{path.name}）"
            )
        print(f"{char} [{contract['lane']}]: condition image ok (MAE={error:.3f})")


def check_app_overlay(contracts: dict) -> None:
    """App 的貼合數字必須跟正式線約定逐字對得上——這就是 7/20 漏掉的那一關。"""
    styles = (ROOT / "web" / "src" / "styles.css").read_text(encoding="utf-8")
    app_js = (ROOT / "web" / "src" / "app.js").read_text(encoding="utf-8")

    overlay = re.search(r"\.fh-overlay\s*\{(.*?)\}", styles, re.S)
    if not overlay:
        raise AssertionError("web/src/styles.css 找不到 .fh-overlay")
    block = overlay.group(1)
    if not re.search(r"aspect-ratio:\s*1\s*/\s*1", block):
        raise AssertionError(
            ".fh-overlay 不再是正方形——正式線的條件圖是原生正方形裁切，"
            "貼回去也必須是正方形，否則頭會被壓扁"
        )

    # app.js：const _box = (_fc === 'a06') ? { top: 'A%' } : { top: 'B%' };  → a06=A、其餘=B
    box_line = re.search(
        r"_box\s*=\s*\(\s*_fc\s*===\s*'a06'\s*\)\s*\?\s*\{\s*top:\s*'([\d.]+)%'\s*\}"
        r"\s*:\s*\{\s*top:\s*'([\d.]+)%'\s*\}",
        app_js,
    )
    if not box_line:
        raise AssertionError("web/src/app.js 找不到臉框的貼合位置（_box）")
    css_tops = {"a06": float(box_line.group(1)), "a05": float(box_line.group(2))}

    # styles.css 的預設值必須跟 app.js 的 a05 分支一致，否則第一幀會貼錯位置再跳一下。
    default_top = _percent(block, r"top:\s*([\d.]+)%")
    if abs(default_top - css_tops["a05"]) > 0.01:
        raise AssertionError(
            f".fh-overlay 預設貼在 {default_top}%，app.js 的 a05 卻是 {css_tops['a05']}%——兩處要一致"
        )

    for char, top_percent in sorted(css_tops.items()):
        contract = contracts[char]
        if contract["lane"] != "prod":
            raise AssertionError(f"{char}: App 只能用正式線的角色代號")
        expected = contract["source_crop"]["y"] / contract["canvas"]["height"] * 100
        if abs(expected - top_percent) > 0.01:
            raise AssertionError(
                f"{char}: App 把臉貼在 {top_percent}%（≈y={round(top_percent / 100 * 1920)}），"
                f"後端宣告 y={contract['source_crop']['y']}（{expected:.6f}%）——兩邊只改了一邊"
            )
        crop = contract["source_crop"]
        if crop["width"] != crop["height"]:
            raise AssertionError(
                f"{char}: 正式線的裁切不是正方形（{crop['width']}x{crop['height']}），"
                "但 App 以 1:1 貼回去 = 頭會被壓扁"
            )
        print(f"{char}: App overlay matches contract (top={top_percent}% = y{crop['y']})")


def _percent(block: str, pattern: str) -> float:
    found = re.search(pattern, block)
    if not found:
        raise AssertionError(f"找不到 {pattern}")
    return float(found.group(1))


def check_demo_lane(contracts: dict) -> None:
    call_html = (ROOT / "munea-b2b" / "call.html").read_text(encoding="utf-8")
    for char in ("a05d", "a06d"):
        if contracts.get(char, {}).get("lane") != "demo":
            raise AssertionError(f"{char} 應該是展示間的實驗格")
        if f"'{char}'" not in call_html:
            raise AssertionError(f"munea-b2b/call.html 沒帶展示間代號 {char}")
    if re.search(r"Face\.start\(\s*curChar\s*\)", call_html):
        raise AssertionError(
            "munea-b2b/call.html 直接把正式線代號送進臉引擎了——展示間的實驗會打到正式 App"
        )
    print("demo lane: isolated from prod chars")


def check_runtime_demo_asset_build() -> None:
    """The shared-card Demo must build its own 768 inputs without touching App assets."""
    tool = ROOT / "deploy" / "runpod-avatar" / "sync-face-assets.py"
    source = ROOT / "munea-b2b" / "flashhead"
    with tempfile.TemporaryDirectory(prefix="munea-demo-assets-") as output:
        child_env = os.environ.copy()
        child_env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [sys.executable, str(tool), "--source", str(source), "--target-dir", output,
             "--lane", "demo", "--frame-size", "768"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=child_env,
        )
        if result.returncode != 0:
            raise AssertionError(
                "Demo 768 runtime asset build failed\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        built = sorted(Path(output).glob("*.png"))
        assert [path.name for path in built] == ["char-a05B-demo.png", "char-a06B-demo.png"]
        for path in built:
            with Image.open(path) as image:
                assert image.size == (768, 768), f"{path.name}: runtime asset is {image.size}"
    print("demo lane: 768 runtime assets build independently")


def main() -> None:
    contracts = engine_contracts()
    check_condition_images(contracts)
    check_app_overlay(contracts)
    check_demo_lane(contracts)
    check_runtime_demo_asset_build()
    print("\nall avatar render contract checks passed")


if __name__ == "__main__":
    main()
