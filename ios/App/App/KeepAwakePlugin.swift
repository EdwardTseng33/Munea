import Capacitor
import UIKit

/// 通話中螢幕不睡（2026-11-08 Edward：「開啟聊聊時應該都要判定是通話中，螢幕不應該跳保護程式」）。
///
/// 長輩跟寧寧聊天時手不會一直碰螢幕，iPhone 預設 30 秒～幾分鐘就變暗、鎖屏，
/// 畫面上的寧寧消失、看起來像斷線。App 在撥號／通話中呼叫 keepAwake，收線呼叫 allowSleep。
///
/// 為什麼不用網頁的螢幕喚醒鎖：iOS 的 App 殼（WKWebView）要很新的系統才支援，舊手機拿不到；
/// 系統的 isIdleTimerDisabled 從 iOS 2 就有，最穩。只在 App 前景有效，切到背景系統自動恢復正常鎖屏。
@objc(KeepAwakePlugin)
public class KeepAwakePlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "KeepAwakePlugin"
    public let jsName = "KeepAwake"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "keepAwake", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "allowSleep", returnType: CAPPluginReturnPromise)
    ]

    @objc func keepAwake(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            UIApplication.shared.isIdleTimerDisabled = true
            call.resolve()
        }
    }

    @objc func allowSleep(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            UIApplication.shared.isIdleTimerDisabled = false
            call.resolve()
        }
    }
}
