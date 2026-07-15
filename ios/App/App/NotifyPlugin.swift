import Foundation
import Capacitor
import UIKit
import UserNotifications

enum MuneaNotificationEvent: String {
    case received = "munea.notification.received"
    case opened = "munea.notification.opened"
    case remoteToken = "munea.notification.remoteToken"
    case registrationError = "munea.notification.registrationError"
}

enum MuneaNotificationBridge {
    private static let pendingLaunchKey = "munea.notification.pendingLaunch"
    private static let remoteTokenKey = "munea.notification.remoteToken"

    static func payload(_ userInfo: [AnyHashable: Any]) -> [String: Any] {
        var result: [String: Any] = [:]
        for key in ["eventId", "eventType", "resourceId", "deepLink"] {
            if let value = userInfo[key] as? String { result[key] = value }
        }
        result["source"] = userInfo["source"] as? String ?? "remote"
        return result
    }

    static func publish(
        _ userInfo: [AnyHashable: Any],
        event: MuneaNotificationEvent,
        persistForLaunch: Bool = false
    ) {
        let value = payload(userInfo)
        if persistForLaunch,
           let data = try? JSONSerialization.data(withJSONObject: value) {
            UserDefaults.standard.set(data, forKey: pendingLaunchKey)
        }
        DispatchQueue.main.async {
            NotificationCenter.default.post(name: Notification.Name(event.rawValue), object: nil, userInfo: value)
        }
    }

    static func storePending(_ userInfo: [AnyHashable: Any]) {
        let value = payload(userInfo)
        if let data = try? JSONSerialization.data(withJSONObject: value) {
            UserDefaults.standard.set(data, forKey: pendingLaunchKey)
        }
    }

    static func publishRemoteToken(_ token: String) {
        let value: [String: Any] = [
            "token": token,
            "environment": apnsEnvironment(),
            "bundleId": Bundle.main.bundleIdentifier ?? "net.munea.app",
            "appVersion": Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "",
        ]
        UserDefaults.standard.set(value, forKey: remoteTokenKey)
        DispatchQueue.main.async {
            NotificationCenter.default.post(
                name: Notification.Name(MuneaNotificationEvent.remoteToken.rawValue),
                object: nil,
                userInfo: value
            )
        }
    }

    static func publishRegistrationError(_ message: String) {
        DispatchQueue.main.async {
            NotificationCenter.default.post(
                name: Notification.Name(MuneaNotificationEvent.registrationError.rawValue),
                object: nil,
                userInfo: ["message": message]
            )
        }
    }

    static func consumePendingLaunch() -> [String: Any]? {
        guard let data = UserDefaults.standard.data(forKey: pendingLaunchKey),
              let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        UserDefaults.standard.removeObject(forKey: pendingLaunchKey)
        return value
    }

    static func savedRemoteToken() -> [String: Any]? {
        UserDefaults.standard.dictionary(forKey: remoteTokenKey)
    }

    static func apnsEnvironment() -> String {
        #if DEBUG
        return "sandbox"
        #else
        return "production"
        #endif
    }
}

/// 沐寧通知橋：本機排程、APNs token、權限狀態與通知點擊事件。
@objc(NotifyPlugin)
public class NotifyPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "NotifyPlugin"
    public let jsName = "Notify"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "requestPermission", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getPermissionStatus", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "registerRemoteNotifications", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getPendingLaunchNotification", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "openSettings", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "scheduleTestNotification", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "sync", returnType: CAPPluginReturnPromise),
    ]

    private let localPrefix = "munea.local."

    override public func load() {
        let center = NotificationCenter.default
        center.addObserver(self, selector: #selector(remoteTokenReceived(_:)), name: Notification.Name(MuneaNotificationEvent.remoteToken.rawValue), object: nil)
        center.addObserver(self, selector: #selector(notificationReceived(_:)), name: Notification.Name(MuneaNotificationEvent.received.rawValue), object: nil)
        center.addObserver(self, selector: #selector(notificationOpened(_:)), name: Notification.Name(MuneaNotificationEvent.opened.rawValue), object: nil)
        center.addObserver(self, selector: #selector(registrationFailed(_:)), name: Notification.Name(MuneaNotificationEvent.registrationError.rawValue), object: nil)
        if let token = MuneaNotificationBridge.savedRemoteToken() {
            notifyListeners("remoteToken", data: token, retainUntilConsumed: true)
        }
        if let launch = MuneaNotificationBridge.consumePendingLaunch() {
            notifyListeners("notificationOpened", data: launch, retainUntilConsumed: true)
        }
    }

    deinit { NotificationCenter.default.removeObserver(self) }

    @objc private func remoteTokenReceived(_ note: Notification) {
        notifyListeners("remoteToken", data: stringKeyed(note.userInfo), retainUntilConsumed: true)
    }

    @objc private func notificationReceived(_ note: Notification) {
        notifyListeners("notificationReceived", data: stringKeyed(note.userInfo))
    }

    @objc private func notificationOpened(_ note: Notification) {
        _ = MuneaNotificationBridge.consumePendingLaunch()
        notifyListeners("notificationOpened", data: stringKeyed(note.userInfo), retainUntilConsumed: true)
    }

    @objc private func registrationFailed(_ note: Notification) {
        notifyListeners("registrationError", data: stringKeyed(note.userInfo))
    }

    private func stringKeyed(_ userInfo: [AnyHashable: Any]?) -> [String: Any] {
        var result: [String: Any] = [:]
        for (key, value) in userInfo ?? [:] {
            if let key = key as? String { result[key] = value }
        }
        return result
    }

    private func permissionValue(_ status: UNAuthorizationStatus) -> String {
        switch status {
        case .denied: return "denied"
        case .authorized: return "authorized"
        case .provisional: return "provisional"
        case .ephemeral: return "ephemeral"
        case .notDetermined: return "not_determined"
        @unknown default: return "not_determined"
        }
    }

    @objc func getPermissionStatus(_ call: CAPPluginCall) {
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            let status = self.permissionValue(settings.authorizationStatus)
            call.resolve([
                "status": status,
                "granted": status == "authorized" || status == "provisional",
                "canAsk": status == "not_determined",
                "canOpenSettings": status == "denied",
            ])
        }
    }

    @objc func requestPermission(_ call: CAPPluginCall) {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, error in
            if let error = error {
                call.reject(error.localizedDescription)
                return
            }
            if granted {
                DispatchQueue.main.async { UIApplication.shared.registerForRemoteNotifications() }
            }
            UNUserNotificationCenter.current().getNotificationSettings { settings in
                call.resolve([
                    "granted": granted,
                    "status": self.permissionValue(settings.authorizationStatus),
                ])
            }
        }
    }

    @objc func registerRemoteNotifications(_ call: CAPPluginCall) {
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            let status = self.permissionValue(settings.authorizationStatus)
            guard status == "authorized" || status == "provisional" else {
                call.resolve(["registered": false, "status": status])
                return
            }
            DispatchQueue.main.async { UIApplication.shared.registerForRemoteNotifications() }
            var result: [String: Any] = ["registered": true, "status": status]
            if let token = MuneaNotificationBridge.savedRemoteToken() { result.merge(token) { _, new in new } }
            call.resolve(result)
        }
    }

    @objc func getPendingLaunchNotification(_ call: CAPPluginCall) {
        if let notification = MuneaNotificationBridge.consumePendingLaunch() {
            call.resolve(["notification": notification])
        } else {
            call.resolve(["notification": NSNull()])
        }
    }

    @objc func openSettings(_ call: CAPPluginCall) {
        guard let url = URL(string: UIApplication.openSettingsURLString) else {
            call.resolve(["opened": false])
            return
        }
        DispatchQueue.main.async {
            UIApplication.shared.open(url, options: [:]) { opened in call.resolve(["opened": opened]) }
        }
    }

    @objc func scheduleTestNotification(_ call: CAPPluginCall) {
        let content = UNMutableNotificationContent()
        content.title = "沐寧測試通知"
        content.body = "通知已設定完成，之後的提醒會出現在這裡。"
        content.sound = .default
        content.userInfo = ["source": "local", "eventType": "test", "deepLink": "munea://notifications"]
        let trigger = UNTimeIntervalNotificationTrigger(timeInterval: 5, repeats: false)
        let request = UNNotificationRequest(identifier: localPrefix + "test", content: content, trigger: trigger)
        UNUserNotificationCenter.current().add(request) { error in
            if let error = error {
                call.reject(error.localizedDescription)
            } else {
                call.resolve(["scheduled": true, "firesInSeconds": 5])
            }
        }
    }

    private func content(for item: [String: Any], showSensitive: Bool) -> UNMutableNotificationContent? {
        let detailTitle = item["title"] as? String ?? "沐寧提醒"
        let detailBody = item["body"] as? String ?? "你有一則新提醒。"
        let publicTitle = item["publicTitle"] as? String ?? "沐寧提醒"
        let publicBody = item["publicBody"] as? String ?? "你的健康提醒到了，解鎖後查看。"
        let content = UNMutableNotificationContent()
        content.title = showSensitive ? detailTitle : publicTitle
        content.body = showSensitive ? detailBody : publicBody
        content.sound = .default
        var userInfo: [String: Any] = ["source": "local"]
        for key in ["eventId", "eventType", "resourceId", "deepLink"] {
            if let value = item[key] as? String { userInfo[key] = value }
        }
        content.userInfo = userInfo
        return content
    }

    private func request(for item: [String: Any], identifier: String, showSensitive: Bool) -> UNNotificationRequest? {
        guard let content = content(for: item, showSensitive: showSensitive),
              let hour = item["hour"] as? Int,
              let minute = item["minute"] as? Int else { return nil }
        var components = DateComponents()
        components.calendar = Calendar(identifier: .gregorian)
        components.timeZone = TimeZone(identifier: item["timezone"] as? String ?? "Asia/Taipei")
        components.hour = hour
        components.minute = minute
        var repeats = item["repeats"] as? Bool ?? false
        if let year = item["year"] as? Int,
           let month = item["month"] as? Int,
           let day = item["day"] as? Int {
            components.year = year
            components.month = month
            components.day = day
            repeats = false
        }
        if let weekday = item["weekday"] as? Int { components.weekday = weekday }
        return UNNotificationRequest(
            identifier: localPrefix + identifier,
            content: content,
            trigger: UNCalendarNotificationTrigger(dateMatching: components, repeats: repeats)
        )
    }

    @objc func sync(_ call: CAPPluginCall) {
        guard let raw = call.getArray("items") else {
            call.reject("缺 items")
            return
        }
        let showSensitive = call.getBool("showSensitiveContent") ?? false
        var requests: [UNNotificationRequest] = []
        for case let item as [String: Any] in raw {
            guard let id = item["id"] as? String else { continue }
            if let weekdays = item["weekdays"] as? [Int], !weekdays.isEmpty {
                for weekday in weekdays where (1...7).contains(weekday) {
                    var weekly = item
                    weekly["weekday"] = weekday
                    weekly["repeats"] = true
                    if let request = request(for: weekly, identifier: id + ".w" + String(weekday), showSensitive: showSensitive) {
                        requests.append(request)
                    }
                }
            } else if let request = request(for: item, identifier: id, showSensitive: showSensitive) {
                requests.append(request)
            }
        }
        let candidateCount = requests.count
        requests = Array(requests.prefix(60))
        let center = UNUserNotificationCenter.current()
        center.getPendingNotificationRequests { pending in
            let oldIds = pending.map(\.identifier).filter { $0.hasPrefix(self.localPrefix) }
            let newIds = Set(requests.map(\.identifier))
            center.removePendingNotificationRequests(withIdentifiers: oldIds.filter { !newIds.contains($0) })
            let group = DispatchGroup()
            let lock = NSLock()
            var scheduled = 0
            var failed = 0
            for request in requests {
                group.enter()
                center.add(request) { error in
                    lock.lock()
                    if error == nil { scheduled += 1 } else { failed += 1 }
                    lock.unlock()
                    group.leave()
                }
            }
            group.notify(queue: .main) {
                call.resolve(["scheduled": scheduled, "failed": failed, "dropped": max(0, candidateCount - requests.count)])
            }
        }
    }
}
