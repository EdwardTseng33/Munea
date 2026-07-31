import Foundation
import Capacitor
import HealthKit
import UIKit

/// 沐寧 · Apple 健康（HealthKit）原生橋接
/// 網頁端透過 Capacitor.Plugins.Health 呼叫：
///   isAvailable()           → 這台裝置有沒有健康資料
///   requestAuthorization()  → 跳系統授權視窗（讀取）
///   getSummary()            → 回傳今天步數 + 最近心率/血氧/血壓 + 昨晚睡眠時數
///   getHistory(days)        → 回傳逐日摘要，供換機與歷史趨勢合併
/// 只讀不寫（第一版）。本外掛本身不上傳，但網頁端會把讀到的數值同步到雲端
/// （app.js → POST /family/state → family_state_entries），供授權的家人查看。
/// 因此健康／健身資料在 App Privacy 問卷申報為「有收集、與身分連結、不用於追蹤」。
@objc(HealthPlugin)
public class HealthPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "HealthPlugin"
    public let jsName = "Health"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "isAvailable", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "requestAuthorization", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getSummary", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getHistory", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "openHealthApp", returnType: CAPPluginReturnPromise)
    ]

    private let store = HKHealthStore()

    private func readTypes() -> Set<HKObjectType> {
        var s = Set<HKObjectType>()
        let quantities: [HKQuantityTypeIdentifier] = [
            .stepCount, .heartRate, .oxygenSaturation,
            .bloodPressureSystolic, .bloodPressureDiastolic
        ]
        for id in quantities {
            if let t = HKObjectType.quantityType(forIdentifier: id) { s.insert(t) }
        }
        if let sleep = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) { s.insert(sleep) }
        return s
    }

    @objc func isAvailable(_ call: CAPPluginCall) {
        call.resolve(["available": HKHealthStore.isHealthDataAvailable()])
    }

    @objc func requestAuthorization(_ call: CAPPluginCall) {
        guard HKHealthStore.isHealthDataAvailable() else {
            call.resolve(["granted": false, "available": false])
            return
        }
        store.requestAuthorization(toShare: nil, read: readTypes()) { success, error in
            if let error = error {
                call.reject(error.localizedDescription)
                return
            }
            call.resolve(["granted": success, "available": true])
        }
    }

    /// 打開「健康」App，讓使用者自己去開項目。
    /// 為什麼需要這個：蘋果的授權視窗**一輩子只跳一次**（同一批項目問過就不再問），
    /// 而且視窗裡的項目**預設全是關的**——很多人直接按「允許」等於一項都沒開。
    /// 之後要補開，唯一的路就是「健康」App →個人照片→「App 與服務」→沐寧。
    /// App 不能代替使用者打開項目（蘋果不給），只能把他送到門口。
    /// 帶使用者去健康 App 開項目。原本只開首頁（x-apple-health://），落地後還要自己找
    /// 「右上頭像 → App 和服務 → 沐寧」三層——長輩幾乎走不完（Edward 2026-07-31 質疑）。
    /// 改成先試 Sources 那一頁（iOS 16 起可用），落地就是來源清單、點一下沐寧就到，少兩層。
    /// 再深一層（直接進沐寧的權限頁）蘋果沒開放，x-apple-health://Sources/<App> 只會停在清單，
    /// 所以最深就到這裡；開不了就退回首頁，絕不讓按鍵變成沒反應。
    @objc func openHealthApp(_ call: CAPPluginCall) {
        let candidates = ["x-apple-health://Sources/", "x-apple-health://"]
        DispatchQueue.main.async {
            for raw in candidates {
                guard let url = URL(string: raw), UIApplication.shared.canOpenURL(url) else { continue }
                UIApplication.shared.open(url, options: [:]) { ok in
                    if ok {
                        call.resolve(["opened": true, "target": raw])
                    } else if raw == candidates.last {
                        call.resolve(["opened": false])
                    }
                }
                return
            }
            call.resolve(["opened": false])
        }
    }

    @objc func getSummary(_ call: CAPPluginCall) {
        guard HKHealthStore.isHealthDataAvailable() else {
            call.resolve(["available": false])
            return
        }
        let group = DispatchGroup()
        var result: [String: Any] = ["available": true]
        // 讀取失敗跟「真的沒有資料」原本長得一模一樣（都只是安靜地什麼都不回），
        // 結果使用者看到空白，我們也查不出是哪一種。這裡把每一項的成敗都記下來回報。
        var readErrors: [String] = []
        let lock = NSLock()
        func put(_ key: String, _ value: Any) {
            lock.lock(); result[key] = value; lock.unlock()
        }
        func note(_ what: String, _ error: Error?) {
            guard let error = error else { return }
            lock.lock(); readErrors.append("\(what): \(error.localizedDescription)"); lock.unlock()
        }

        // 今天步數（累加）
        if let stepType = HKQuantityType.quantityType(forIdentifier: .stepCount) {
            group.enter()
            let start = Calendar.current.startOfDay(for: Date())
            let pred = HKQuery.predicateForSamples(withStart: start, end: Date(), options: .strictStartDate)
            let q = HKStatisticsQuery(quantityType: stepType, quantitySamplePredicate: pred, options: .cumulativeSum) { _, stats, error in
                note("steps", error)
                if let sum = stats?.sumQuantity() {
                    put("steps", Int(sum.doubleValue(for: HKUnit.count())))
                }
                group.leave()
            }
            store.execute(q)
        }

        // 最近一次心率（次/分）
        if let hrType = HKQuantityType.quantityType(forIdentifier: .heartRate) {
            group.enter()
            latestQuantity(hrType) { qty, error in
                note("hr", error)
                if let qty = qty {
                    put("hr", Int(qty.doubleValue(for: HKUnit.count().unitDivided(by: HKUnit.minute())).rounded()))
                }
                group.leave()
            }
        }

        // 最近一次血氧（%）
        if let spo2Type = HKQuantityType.quantityType(forIdentifier: .oxygenSaturation) {
            group.enter()
            latestQuantity(spo2Type) { qty, error in
                note("spo2", error)
                if let qty = qty {
                    put("spo2", Int((qty.doubleValue(for: HKUnit.percent()) * 100).rounded()))
                }
                group.leave()
            }
        }

        // 最近一次血壓（收縮 / 舒張，mmHg）
        if let sysType = HKQuantityType.quantityType(forIdentifier: .bloodPressureSystolic) {
            group.enter()
            latestQuantity(sysType) { qty, error in
                note("bpSys", error)
                if let qty = qty { put("bpSys", Int(qty.doubleValue(for: HKUnit.millimeterOfMercury()).rounded())) }
                group.leave()
            }
        }
        if let diaType = HKQuantityType.quantityType(forIdentifier: .bloodPressureDiastolic) {
            group.enter()
            latestQuantity(diaType) { qty, error in
                note("bpDia", error)
                if let qty = qty { put("bpDia", Int(qty.doubleValue(for: HKUnit.millimeterOfMercury()).rounded())) }
                group.leave()
            }
        }

        // 昨晚睡眠（近 24 小時內「睡著」時段的總時數）
        if let sleepType = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) {
            group.enter()
            let end = Date()
            let start = Calendar.current.date(byAdding: .hour, value: -24, to: end) ?? end
            let pred = HKQuery.predicateForSamples(withStart: start, end: end, options: [])
            let q = HKSampleQuery(sampleType: sleepType, predicate: pred, limit: HKObjectQueryNoLimit, sortDescriptors: nil) { _, samples, error in
                note("sleep", error)
                var secs = 0.0
                if let samples = samples as? [HKCategorySample] {
                    for s in samples where self.isAsleep(s.value) {
                        secs += s.endDate.timeIntervalSince(s.startDate)
                    }
                }
                if secs > 0 { put("sleepHours", (secs / 3600.0 * 10).rounded() / 10) }
                group.leave()
            }
            store.execute(q)
        }

        group.notify(queue: .main) {
            // 讀到哪幾項、哪幾項出錯，一起回報。網頁端才分得出「沒資料」跟「讀失敗」。
            lock.lock()
            let fields = ["steps", "hr", "spo2", "bpSys", "bpDia", "sleepHours"].filter { result[$0] != nil }
            result["fields"] = fields
            result["errors"] = readErrors
            result["readAt"] = Date().timeIntervalSince1970 * 1000
            lock.unlock()
            call.resolve(result)
        }
    }

    @objc func getHistory(_ call: CAPPluginCall) {
        guard HKHealthStore.isHealthDataAvailable() else {
            call.resolve(["available": false, "days": []])
            return
        }
        let rangeDays = max(1, min(call.getInt("days") ?? 35, 365))
        let calendar = Calendar.current
        let end = Date()
        let startDay = calendar.startOfDay(for: calendar.date(byAdding: .day, value: -(rangeDays - 1), to: end) ?? end)
        let predicate = HKQuery.predicateForSamples(withStart: startDay, end: end, options: [])
        let group = DispatchGroup()
        let lock = NSLock()
        var daily: [String: [String: Any]] = [:]

        func key(_ date: Date) -> String {
            let c = calendar.dateComponents([.year, .month, .day], from: date)
            return String(format: "%04d-%02d-%02d", c.year ?? 0, c.month ?? 0, c.day ?? 0)
        }
        func put(_ date: Date, _ field: String, _ value: Any) {
            let day = key(date)
            lock.lock()
            var row = daily[day] ?? ["date": day]
            row[field] = value
            daily[day] = row
            lock.unlock()
        }

        // Statistics avoid double-counting overlapping phone/watch step samples.
        if let stepType = HKQuantityType.quantityType(forIdentifier: .stepCount) {
            group.enter()
            let query = HKStatisticsCollectionQuery(
                quantityType: stepType,
                quantitySamplePredicate: predicate,
                options: .cumulativeSum,
                anchorDate: startDay,
                intervalComponents: DateComponents(day: 1)
            )
            query.initialResultsHandler = { _, results, _ in
                results?.enumerateStatistics(from: startDay, to: end) { stats, _ in
                    if let sum = stats.sumQuantity() {
                        put(stats.startDate, "steps", Int(sum.doubleValue(for: HKUnit.count()).rounded()))
                    }
                }
                group.leave()
            }
            store.execute(query)
        }

        func latestPerDay(_ identifier: HKQuantityTypeIdentifier, field: String, unit: HKUnit, multiplier: Double = 1) {
            guard let type = HKQuantityType.quantityType(forIdentifier: identifier) else { return }
            group.enter()
            let sort = NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: true)
            let query = HKSampleQuery(sampleType: type, predicate: predicate, limit: HKObjectQueryNoLimit, sortDescriptors: [sort]) { _, samples, _ in
                for sample in (samples as? [HKQuantitySample]) ?? [] {
                    put(sample.endDate, field, Int((sample.quantity.doubleValue(for: unit) * multiplier).rounded()))
                }
                group.leave()
            }
            store.execute(query)
        }

        latestPerDay(.heartRate, field: "hr", unit: HKUnit.count().unitDivided(by: HKUnit.minute()))
        latestPerDay(.oxygenSaturation, field: "spo2", unit: HKUnit.percent(), multiplier: 100)
        latestPerDay(.bloodPressureSystolic, field: "bpSys", unit: HKUnit.millimeterOfMercury())
        latestPerDay(.bloodPressureDiastolic, field: "bpDia", unit: HKUnit.millimeterOfMercury())

        if let sleepType = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) {
            group.enter()
            let query = HKSampleQuery(sampleType: sleepType, predicate: predicate, limit: HKObjectQueryNoLimit, sortDescriptors: nil) { _, samples, _ in
                var seconds: [String: Double] = [:]
                for sample in (samples as? [HKCategorySample]) ?? [] where self.isAsleep(sample.value) {
                    seconds[key(sample.endDate), default: 0] += sample.endDate.timeIntervalSince(sample.startDate)
                }
                lock.lock()
                for (day, value) in seconds {
                    var row = daily[day] ?? ["date": day]
                    row["sleepHours"] = (value / 3600.0 * 10).rounded() / 10
                    daily[day] = row
                }
                lock.unlock()
                group.leave()
            }
            store.execute(query)
        }

        group.notify(queue: .main) {
            let rows = daily.keys.sorted().compactMap { daily[$0] }
            call.resolve(["available": true, "rangeDays": rangeDays, "days": rows])
        }
    }

    /// 判斷睡眠樣本是否為「睡著」（相容 iOS 16 前後的分類值）
    private func isAsleep(_ value: Int) -> Bool {
        if #available(iOS 16.0, *) {
            return value == HKCategoryValueSleepAnalysis.asleepCore.rawValue
                || value == HKCategoryValueSleepAnalysis.asleepDeep.rawValue
                || value == HKCategoryValueSleepAnalysis.asleepREM.rawValue
                || value == HKCategoryValueSleepAnalysis.asleepUnspecified.rawValue
        } else {
            return value == HKCategoryValueSleepAnalysis.asleep.rawValue
        }
    }

    /// 讀「最近一筆」某種量測值
    /// 限最近 7 天內：狀態頁把這些值標成「今天」，沒有時間界線的話，
    /// 幾個月前的舊紀錄會被當成今天的數值顯示（長輩會以為是剛量的）。
    private func latestQuantity(_ type: HKQuantityType, completion: @escaping (HKQuantity?, Error?) -> Void) {
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: false)
        let end = Date()
        let start = Calendar.current.date(byAdding: .day, value: -7, to: end) ?? end
        let recent = HKQuery.predicateForSamples(withStart: start, end: end, options: [])
        let q = HKSampleQuery(sampleType: type, predicate: recent, limit: 1, sortDescriptors: [sort]) { _, samples, error in
            completion((samples?.first as? HKQuantitySample)?.quantity, error)
        }
        store.execute(q)
    }
}
