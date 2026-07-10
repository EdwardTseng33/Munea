# -*- coding: utf-8 -*-
"""FlashHead 真機測試頁 · 純靜態小網站（2026-07-10 · 卡西法）
只做一件事：把 web/flashhead-live-test.html + 兩張背景圖用 HTTPS 端出去，
給 Edward 手機直接開。不碰 munea-voice-staging（Cloud Run 部署權限這輪被擋、
改用同一個已核准的 Modal 帳號另開一個乾淨小 App，不影響任何現役服務）。
頁面本身連線目標：
  - FlashHead 臉引擎：munea-flashhead-avatar-dev（獨立 GPU 服務，本檔不碰）
  - 語音橋：munea-voice-staging（既有 Cloud Run 服務，本檔只是「連過去」不「部署它」）
用法：modal deploy -m flashhead_test_page
"""
import modal

app = modal.App("munea-flashhead-test-page")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fastapi")
    .add_local_file(r"E:\Claude\Munea\web\flashhead-live-test.html", "/root/page.html")
    .add_local_file(r"E:\Claude\Munea\web\flashhead\bg-a05.png", "/root/bg-a05.png")
    .add_local_file(r"E:\Claude\Munea\web\flashhead\bg-a06.png", "/root/bg-a06.png")
    .add_local_file(r"E:\Claude\Munea\web\flashhead\greet-a05.mp4", "/root/greet-a05.mp4")
)


@app.function(image=image, max_containers=1)
@modal.asgi_app()
def web():
    from fastapi import FastAPI
    from fastapi.responses import FileResponse

    api = FastAPI()

    @api.get("/")
    def index():
        # 測試迭代期不快取，確保每次修完 Edward 開到的都是最新版（不必自己 ?_cb= 破快取）
        return FileResponse("/root/page.html", media_type="text/html; charset=utf-8",
                            headers={"Cache-Control": "no-store, must-revalidate"})

    # 2026-07-11 卡西法：三個資產路由原本沒帶 Cache-Control，Modal 掛載檔案的 Last-Modified
    # 又是 epoch(1970-01-01，add_local_file 沒保留真實 mtime)——瀏覽器的 heuristic caching
    # 會把這當「非常久以前修改過、可以放心快取很久」，換資產（例如這輪 greet-a05.mp4 從舊
    # 512 特寫版換成 comp7 全幅版）URL 沒變，同一支瀏覽器早跑過這頁就可能吃到自己本地快取的
    # 舊檔案，看起來像「部署沒生效」，其實是「瀏覽器沒重新要」。跟 index() 一樣一律 no-store。
    _NO_CACHE = {"Cache-Control": "no-store, must-revalidate"}

    @api.get("/flashhead/bg-a05.png")
    def bg05():
        return FileResponse("/root/bg-a05.png", media_type="image/png", headers=_NO_CACHE)

    @api.get("/flashhead/bg-a06.png")
    def bg06():
        return FileResponse("/root/bg-a06.png", media_type="image/png", headers=_NO_CACHE)

    @api.get("/flashhead/greet-a05.mp4")
    def greeta05():
        return FileResponse("/root/greet-a05.mp4", media_type="video/mp4", headers=_NO_CACHE)

    return api
