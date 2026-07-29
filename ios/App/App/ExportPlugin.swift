import Capacitor
import UIKit
import WebKit

/// 就診摘要匯出（M1 · PR-4d）——把一段 HTML 算成 PDF，交給系統分享面板。
///
/// **為什麼要寫這支原生外掛，而不是用 `window.print()`：**
/// `window.print()` 在 iOS 的 WKWebView **完全無效**——同一顆按鈕在 iOS Safari 可以，
/// 在 App 殼裡按了沒反應（Apple 開發者論壇多方證實，SwiftUI WebView 同樣不支援列印，
/// 官方建議「改成輸出 PDF 或圖片」）。留著那顆按鈕等於給長輩一個按了沒事的東西，
/// 比沒有更糟——他會以為是自己按錯。
///
/// **為什麼不用 JS 的 PDF 套件（jsPDF／html2canvas 之類）：**
/// 那些套件預設不含中文字型，不是變亂碼就是要把一份字型檔塞進 App（肥很多），
/// 而且是新的第三方依賴。用系統 API 中文由 iOS 自己渲染，一個字都不會錯，零依賴、零成本。
///
/// **為什麼另開一個離屏 WKWebView，而不是直接印主畫面：**
/// 摘要面板是可滾動的 modal。直接對主 webview 呼叫 createPDF，拿到的是整個 App 畫面
/// （含分頁列、含被裁掉的捲動內容）。改成餵一段「純摘要 HTML」進一個離屏 webview，
/// 版面完全可控、跟 App 的殼無關，也不會因為使用者捲到哪就印出不一樣的東西。
///
/// 出來的 PDF 交給 UIActivityViewController：存到「檔案」、傳 LINE、AirDrop、
/// 真的用 AirPrint 印出來——一個面板全包，不用我們各做一顆按鈕。
@objc(ExportPlugin)
public class ExportPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "ExportPlugin"
    public let jsName = "Export"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "sharePdf", returnType: CAPPluginReturnPromise)
    ]

    /// 離屏 webview 要留著強參照，否則還沒算完就被回收 → completion 永遠不會來。
    private var renderer: WKWebView?
    private var pendingCall: CAPPluginCall?

    @objc func sharePdf(_ call: CAPPluginCall) {
        let html = call.getString("html") ?? ""
        // 檔名會出現在分享面板與「檔案」App 裡，讓長輩認得出這是什麼
        let rawName = call.getString("filename")
            ?? muneaNativeText("native.export.defaultFilename", "就診摘要")
        let filename = Self.safeFilename(rawName)

        guard !html.isEmpty else {
            call.reject(
                muneaNativeText("native.export.emptyContent", "沒有可以匯出的內容"),
                "export_empty_html"
            )
            return
        }

        DispatchQueue.main.async {
            guard self.pendingCall == nil else {
                call.reject(
                    muneaNativeText("native.export.inProgress", "正在匯出中，請稍候"),
                    "export_in_progress"
                )
                return
            }
            guard let presenter = self.bridge?.viewController else {
                call.reject(
                    muneaNativeText("native.common.viewUnavailable", "找不到目前的 App 畫面"),
                    "export_view_unavailable"
                )
                return
            }
            self.pendingCall = call

            // A4 直式（點，72dpi）。固定寬度＝版面不隨裝置大小跑掉，醫師拿到的每一份長一樣。
            let pageWidth: CGFloat = 595
            let pageHeight: CGFloat = 842
            let webView = WKWebView(frame: CGRect(x: 0, y: 0, width: pageWidth, height: pageHeight))
            webView.isOpaque = true
            webView.backgroundColor = .white
            webView.navigationDelegate = self
            self.renderer = webView

            // 必須真的掛進畫面階層，否則 WKWebView 可能根本不排版 → createPDF 拿到空白。
            // 完全透明＋不吃點擊＋壓到最底，使用者看不到也碰不到，只是為了讓它真的算版面。
            webView.alpha = 0
            webView.isUserInteractionEnabled = false
            presenter.view.addSubview(webView)
            presenter.view.sendSubviewToBack(webView)
            // baseURL 給 nil：這段 HTML 是我們自己組的、自帶樣式，不該去載任何外部資源。
            webView.loadHTMLString(html, baseURL: nil)

            // 保險絲：萬一 didFinish 永遠不來（載入卡住），不要讓使用者的按鈕永遠轉圈。
            DispatchQueue.main.asyncAfter(deadline: .now() + 12) { [weak self] in
                guard let self, let pending = self.pendingCall else { return }
                self.cleanup()
                pending.reject(
                    muneaNativeText("native.export.renderTimeout", "這一頁轉檔花太久，請再試一次"),
                    "export_render_timeout"
                )
            }

            self.presenterRef = presenter
            self.pendingFilename = filename
        }
    }

    private var presenterRef: UIViewController?
    private var pendingFilename: String = muneaNativeText("native.export.defaultFilename", "就診摘要")

    private func cleanup() {
        renderer?.navigationDelegate = nil
        renderer?.removeFromSuperview()   // 掛上去就要拿下來，不然每匯出一次就留一個殭屍 webview
        renderer = nil
        pendingCall = nil
        presenterRef = nil
    }

    /// 檔名守門：路徑分隔字元與控制字元一律換掉，避免寫到預期外的位置。
    private static func safeFilename(_ raw: String) -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let cleaned = trimmed.components(separatedBy: CharacterSet(charactersIn: "/\\:*?\"<>|\n\r\t"))
            .joined(separator: "-")
        let limited = String(cleaned.prefix(40))
        return limited.isEmpty
            ? muneaNativeText("native.export.defaultFilename", "就診摘要")
            : limited
    }
}

extension ExportPlugin: WKNavigationDelegate {
    public func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard pendingCall != nil, let presenter = presenterRef else { return }
        let filename = pendingFilename

        // 版面排完才算得對——排版還沒跑完就 createPDF 會拿到半成品。
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { [weak self] in
            guard let self, self.pendingCall != nil else { return }
            let config = WKPDFConfiguration()   // rect 不設＝整份內容，不是只有可視區
            webView.createPDF(configuration: config) { result in
                guard let pending = self.pendingCall else { return }
                switch result {
                case .failure(let error):
                    self.cleanup()
                    pending.reject(
                        muneaNativeText("native.export.pdfFailed", "轉成 PDF 失敗"),
                        "export_pdf_failed",
                        error
                    )
                case .success(let data):
                    let url = FileManager.default.temporaryDirectory
                        .appendingPathComponent("\(filename).pdf")
                    do {
                        try data.write(to: url, options: .atomic)
                    } catch {
                        self.cleanup()
                        pending.reject(
                            muneaNativeText("native.export.writeFailed", "檔案存不起來"),
                            "export_write_failed",
                            error
                        )
                        return
                    }
                    let sheet = UIActivityViewController(activityItems: [url], applicationActivities: nil)
                    // iPad 一定要給 anchor，否則彈出來會直接崩潰
                    if let pop = sheet.popoverPresentationController {
                        pop.sourceView = presenter.view
                        pop.sourceRect = CGRect(
                            x: presenter.view.bounds.midX, y: presenter.view.bounds.midY,
                            width: 0, height: 0
                        )
                        pop.permittedArrowDirections = []
                    }
                    sheet.completionWithItemsHandler = { activity, completed, _, _ in
                        // 只回報「有沒有完成、用了哪個管道」——**不回報傳給了誰**。
                        // 那是健康資料的去向，不該進我們的紀錄。
                        pending.resolve([
                            "ok": true,
                            "completed": completed,
                            "activity": activity?.rawValue ?? "",
                        ])
                    }
                    self.pendingCall = nil   // 面板已交出去，保險絲不該再開火
                    presenter.present(sheet, animated: true)
                    self.renderer?.navigationDelegate = nil
                    self.renderer?.removeFromSuperview()
                    self.renderer = nil
                    self.presenterRef = nil
                }
            }
        }
    }

    public func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        guard let pending = pendingCall else { return }
        cleanup()
        pending.reject(
            muneaNativeText("native.export.loadFailed", "這一頁載入失敗"),
            "export_load_failed",
            error
        )
    }
}
