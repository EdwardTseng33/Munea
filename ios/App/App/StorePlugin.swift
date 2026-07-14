import Foundation
import Capacitor
import StoreKit
import UIKit

/// 沐寧 · 蘋果內購（StoreKit 2）原生橋接
/// 網頁端透過 Capacitor.Plugins.Store 呼叫：
///   getProducts({ids:[...]})   → 讀 App Store Connect 商品（在地化價格）
///   purchase({productId})      → 跳蘋果付款視窗 → {state:'purchased'|'cancelled'|'pending'|...}
///   restore()                  → 找回這個 Apple ID 有效的訂閱（換手機/重裝用）
/// 續訂、家長核准等背景到帳 → 發 'purchase' 事件給網頁。
@objc(StorePlugin)
public class StorePlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "StorePlugin"
    public let jsName = "Store"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "getProducts", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "purchase", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "restore", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "manageSubscriptions", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "finish", returnType: CAPPluginReturnPromise)
    ]

    private var updatesTask: Task<Void, Never>?

    override public func load() {
        // 背景到帳（自動續訂、離線完成的交易）：結單＋通知網頁生效
        updatesTask = Task {
            for await result in Transaction.updates {
                if case .verified(let t) = result {
                    self.notifyListeners("purchase", data: [
                        "productId": t.productID,
                        "transactionId": String(t.id),
                        "originalTransactionId": String(t.originalID),
                        "signedTransaction": result.jwsRepresentation
                    ])
                }
            }
        }
    }

    deinit { updatesTask?.cancel() }

    @objc func getProducts(_ call: CAPPluginCall) {
        let ids = call.getArray("ids", String.self) ?? []
        Task {
            do {
                let prods = try await Product.products(for: ids)
                let arr: [[String: String]] = prods.map {
                    ["id": $0.id, "displayPrice": $0.displayPrice, "title": $0.displayName]
                }
                call.resolve(["products": arr])
            } catch {
                call.reject(error.localizedDescription)
            }
        }
    }

    @objc func purchase(_ call: CAPPluginCall) {
        guard let pid = call.getString("productId"), !pid.isEmpty else {
            call.reject("缺 productId")
            return
        }
        Task {
            do {
                guard let product = try await Product.products(for: [pid]).first else {
                    call.resolve(["state": "notfound", "productId": pid])
                    return
                }
                let accountToken = call.getString("appAccountToken").flatMap(UUID.init(uuidString:))
                let result: Product.PurchaseResult
                if let accountToken {
                    result = try await product.purchase(options: [.appAccountToken(accountToken)])
                } else {
                    result = try await product.purchase()
                }
                switch result {
                case .success(let verification):
                    switch verification {
                    case .verified(let t):
                        call.resolve([
                            "state": "purchased",
                            "productId": t.productID,
                            "transactionId": String(t.id),
                            "originalTransactionId": String(t.originalID),
                            "signedTransaction": verification.jwsRepresentation
                        ])
                    case .unverified:
                        call.resolve(["state": "unverified", "productId": pid])
                    }
                case .userCancelled:
                    call.resolve(["state": "cancelled", "productId": pid])
                case .pending:
                    // 例如「請家人核准」：核准後走 Transaction.updates 到帳
                    call.resolve(["state": "pending", "productId": pid])
                @unknown default:
                    call.resolve(["state": "unknown", "productId": pid])
                }
            } catch {
                call.reject(error.localizedDescription)
            }
        }
    }

    @objc func restore(_ call: CAPPluginCall) {
        Task {
            var ids: [String] = []
            var transactions: [[String: String]] = []
            for await result in Transaction.currentEntitlements {
                if case .verified(let t) = result {
                    ids.append(t.productID)
                    transactions.append([
                        "productId": t.productID,
                        "transactionId": String(t.id),
                        "originalTransactionId": String(t.originalID),
                        "signedTransaction": result.jwsRepresentation
                    ])
                }
            }
            call.resolve(["productIds": ids, "transactions": transactions])
        }
    }

    @objc func manageSubscriptions(_ call: CAPPluginCall) {
        Task { @MainActor in
            let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
            guard let scene = scenes.first(where: { $0.activationState == .foregroundActive }) ?? scenes.first else {
                call.reject("找不到目前的 App 視窗")
                return
            }
            do {
                try await AppStore.showManageSubscriptions(in: scene)
                call.resolve(["ok": true])
            } catch {
                call.reject(error.localizedDescription)
            }
        }
    }

    @objc func finish(_ call: CAPPluginCall) {
        guard let rawId = call.getString("transactionId"), let transactionId = UInt64(rawId) else {
            call.reject("缺 transactionId")
            return
        }
        Task {
            for await result in Transaction.unfinished {
                if case .verified(let transaction) = result, transaction.id == transactionId {
                    await transaction.finish()
                    call.resolve(["ok": true])
                    return
                }
            }
            call.resolve(["ok": true, "alreadyFinished": true])
        }
    }
}
