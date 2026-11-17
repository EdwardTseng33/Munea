import AVFoundation
import Capacitor
import UIKit
import WebKit

/// 聲音工作階段救援（2026-11-16）。
///
/// 真機病徵（2026-11-13，App 1.0.71）：通話中把 App 切到背景再回來，下一通的聲音引擎
/// 自稱在跑、時鐘卻停在 0，麥克風一包都送不出去；把 App 整個關掉重開才好。
///
/// 為什麼需要原生層：網頁（WKWebView）的收音與播放其實跑在系統另外開的行程裡，
/// 有它自己的聲音工作階段；網頁這層把引擎、麥克風全部換新也碰不到它。
/// 本外掛從 App 外殼這邊做兩件事，讓網頁在「撥號前發現時鐘不走」時可以叫：
///
///   1. reactivate()：外殼自己的聲音工作階段「開一下再關掉並通知其他人」。
///      外殼的工作階段一啟用，系統會把網頁那邊的工作階段打斷；外殼關掉並通知後，
///      系統會請網頁那邊恢復——等於請系統把網頁的收放音重新走一遍。
///      ⚠ 一定要關回去：外殼的工作階段若一直開著，反而會壓住網頁的收音。
///      ⚠ 所以不在「每次回到前景」自動做：正在講的通話會被打斷、使用者在聽的音樂會被停掉。
///        只有網頁量到時鐘不走、已經沒有東西可以失去時才做。
///   2. 回到前景時，如果系統把網頁的麥克風標成「靜音」，用官方介面把它打開
///      （這個動作不會打斷任何聲音，所以可以每次都做）。
///
/// 只回報狀態字串與布林值，不碰、不記錄任何聲音內容。
/// 這招到底有沒有效，要靠真機通話後的診斷事件才知道（見網頁端 voice_audio_clock_step）。
@objc(AudioSessionPlugin)
public class AudioSessionPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "AudioSessionPlugin"
    public let jsName = "AudioSession"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "status", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "reactivate", returnType: CAPPluginReturnPromise)
    ]

    private var captureAtResign = "unknown"
    private var captureAtResume = "unknown"
    private var resumeUnmuted = false
    private var resumeCount = 0

    override public func load() {
        let center = NotificationCenter.default
        center.addObserver(self, selector: #selector(appWillResignActive), name: UIApplication.willResignActiveNotification, object: nil)
        center.addObserver(self, selector: #selector(appDidBecomeActive), name: UIApplication.didBecomeActiveNotification, object: nil)
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    private func captureName(_ state: WKMediaCaptureState) -> String {
        switch state {
        case .none: return "none"
        case .active: return "active"
        case .muted: return "muted"
        @unknown default: return "unknown"
        }
    }

    /// 只能在主執行緒呼叫（讀的是畫面上那個網頁元件的狀態）。
    private func currentCapture() -> String {
        guard let webView = bridge?.webView else { return "unavailable" }
        return captureName(webView.microphoneCaptureState)
    }

    @objc private func appWillResignActive() {
        captureAtResign = currentCapture()
    }

    @objc private func appDidBecomeActive() {
        resumeCount += 1
        resumeUnmuted = false
        guard let webView = bridge?.webView else {
            captureAtResume = "unavailable"
            return
        }
        let state = webView.microphoneCaptureState
        captureAtResume = captureName(state)
        if state == .muted {
            resumeUnmuted = true
            webView.setMicrophoneCaptureState(.active, completionHandler: nil)
        }
    }

    @objc func status(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            call.resolve([
                "capture": self.currentCapture(),
                "captureAtResign": self.captureAtResign,
                "captureAtResume": self.captureAtResume,
                "resumeUnmuted": self.resumeUnmuted,
                "resumeCount": self.resumeCount
            ])
        }
    }

    @objc func reactivate(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            let captureBefore = self.currentCapture()
            // 啟用／停用聲音工作階段會卡住呼叫的執行緒，不放在主執行緒做。
            DispatchQueue.global(qos: .userInitiated).async {
                let session = AVAudioSession.sharedInstance()
                var failedStep = ""
                var errorCode = 0
                var pulsed = false
                do {
                    failedStep = "category"
                    try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker])
                    failedStep = "activate"
                    try session.setActive(true)
                    // 留一小段時間，讓系統真的把「被打斷」送到網頁那邊，再放手。
                    Thread.sleep(forTimeInterval: 0.15)
                    failedStep = "deactivate"
                    try session.setActive(false, options: .notifyOthersOnDeactivation)
                    failedStep = ""
                    pulsed = true
                } catch {
                    errorCode = (error as NSError).code
                    // 不管卡在哪一步，都不可以把外殼的工作階段留在啟用狀態。
                    try? session.setActive(false, options: .notifyOthersOnDeactivation)
                }
                let resultPulsed = pulsed
                let resultFailedStep = failedStep
                let resultErrorCode = errorCode
                DispatchQueue.main.async {
                    let finish: (Bool) -> Void = { unmuted in
                        call.resolve([
                            "pulsed": resultPulsed,
                            "failedStep": resultFailedStep,
                            "errorCode": resultErrorCode,
                            "captureBefore": captureBefore,
                            "captureAfter": self.currentCapture(),
                            "unmuted": unmuted,
                            "captureAtResign": self.captureAtResign,
                            "captureAtResume": self.captureAtResume,
                            "resumeUnmuted": self.resumeUnmuted
                        ])
                    }
                    if let webView = self.bridge?.webView, webView.microphoneCaptureState == .muted {
                        webView.setMicrophoneCaptureState(.active) {
                            finish(true)
                        }
                    } else {
                        finish(false)
                    }
                }
            }
        }
    }
}
