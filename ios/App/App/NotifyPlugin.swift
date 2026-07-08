import Foundation
import Capacitor
import UserNotifications

/// 沐寧 · 本機提醒通知（App 關著也會到點響）
/// 網頁端透過 Capacitor.Plugins.Notify 呼叫：
///   requestPermission() → 跳系統通知授權
///   sync({items:[...]}) → 整批重排（先清後排）：
///     每日重複：{id,title,body,hour,minute,repeats:true}（吃藥提醒）
///     單次：    {id,title,body,year,month,day,hour,minute}（回診提醒）
@objc(NotifyPlugin)
public class NotifyPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "NotifyPlugin"
    public let jsName = "Notify"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "requestPermission", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "sync", returnType: CAPPluginReturnPromise)
    ]

    @objc func requestPermission(_ call: CAPPluginCall) {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
            call.resolve(["granted": granted])
        }
    }

    @objc func sync(_ call: CAPPluginCall) {
        guard let raw = call.getArray("items") else {
            call.reject("缺 items")
            return
        }
        let center = UNUserNotificationCenter.current()
        center.removeAllPendingNotificationRequests()
        var scheduled = 0
        for case let it as [String: Any] in raw {
            guard let id = it["id"] as? String,
                  let title = it["title"] as? String,
                  let body = it["body"] as? String,
                  let hour = it["hour"] as? Int,
                  let minute = it["minute"] as? Int else { continue }
            var comps = DateComponents()
            comps.hour = hour
            comps.minute = minute
            var repeats = (it["repeats"] as? Bool) ?? false
            if let y = it["year"] as? Int, let mo = it["month"] as? Int, let d = it["day"] as? Int {
                comps.year = y; comps.month = mo; comps.day = d
                repeats = false
            }
            let content = UNMutableNotificationContent()
            content.title = title
            content.body = body
            content.sound = .default
            let trigger = UNCalendarNotificationTrigger(dateMatching: comps, repeats: repeats)
            center.add(UNNotificationRequest(identifier: id, content: content, trigger: trigger))
            scheduled += 1
        }
        call.resolve(["scheduled": scheduled])
    }
}
