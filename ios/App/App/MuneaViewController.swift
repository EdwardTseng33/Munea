import UIKit
import Capacitor

/// 沐寧主畫面：明確把 App 自帶的原生外掛掛上橋（不靠自動掃描，保證載入）
class MuneaViewController: CAPBridgeViewController {
    override open func capacitorDidLoad() {
        bridge?.registerPluginInstance(HealthPlugin())
        bridge?.registerPluginInstance(StorePlugin())
        bridge?.registerPluginInstance(NotifyPlugin())
        bridge?.registerPluginInstance(AppleSignInPlugin())
        bridge?.registerPluginInstance(GoogleSignInPlugin())
    }
}
