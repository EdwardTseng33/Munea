import Foundation
import Capacitor
import HealthKit

/// 沐寧 · Apple 健康（HealthKit）原生橋接
/// 網頁端透過 Capacitor.Plugins.Health 呼叫：
///   isAvailable()           → 這台裝置有沒有健康資料
///   requestAuthorization()  → 跳系統授權視窗（讀取）
///   getSummary()            → 回傳今天步數 + 最近心率/血氧/血壓 + 昨晚睡眠時數
/// 只讀不寫（第一版）。資料留在裝置端，交給網頁決定怎麼呈現。
@objc(HealthPlugin)
public class HealthPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "HealthPlugin"
    public let jsName = "Health"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "isAvailable", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "requestAuthorization", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getSummary", returnType: CAPPluginReturnPromise)
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

    @objc func getSummary(_ call: CAPPluginCall) {
        guard HKHealthStore.isHealthDataAvailable() else {
            call.resolve(["available": false])
            return
        }
        let group = DispatchGroup()
        var result: [String: Any] = ["available": true]
        let lock = NSLock()
        func put(_ key: String, _ value: Any) {
            lock.lock(); result[key] = value; lock.unlock()
        }

        // 今天步數（累加）
        if let stepType = HKQuantityType.quantityType(forIdentifier: .stepCount) {
            group.enter()
            let start = Calendar.current.startOfDay(for: Date())
            let pred = HKQuery.predicateForSamples(withStart: start, end: Date(), options: .strictStartDate)
            let q = HKStatisticsQuery(quantityType: stepType, quantitySamplePredicate: pred, options: .cumulativeSum) { _, stats, _ in
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
            latestQuantity(hrType) { qty in
                if let qty = qty {
                    put("hr", Int(qty.doubleValue(for: HKUnit.count().unitDivided(by: HKUnit.minute())).rounded()))
                }
                group.leave()
            }
        }

        // 最近一次血氧（%）
        if let spo2Type = HKQuantityType.quantityType(forIdentifier: .oxygenSaturation) {
            group.enter()
            latestQuantity(spo2Type) { qty in
                if let qty = qty {
                    put("spo2", Int((qty.doubleValue(for: HKUnit.percent()) * 100).rounded()))
                }
                group.leave()
            }
        }

        // 最近一次血壓（收縮 / 舒張，mmHg）
        if let sysType = HKQuantityType.quantityType(forIdentifier: .bloodPressureSystolic) {
            group.enter()
            latestQuantity(sysType) { qty in
                if let qty = qty { put("bpSys", Int(qty.doubleValue(for: HKUnit.millimeterOfMercury()).rounded())) }
                group.leave()
            }
        }
        if let diaType = HKQuantityType.quantityType(forIdentifier: .bloodPressureDiastolic) {
            group.enter()
            latestQuantity(diaType) { qty in
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
            let q = HKSampleQuery(sampleType: sleepType, predicate: pred, limit: HKObjectQueryNoLimit, sortDescriptors: nil) { _, samples, _ in
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
            call.resolve(result)
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
    private func latestQuantity(_ type: HKQuantityType, completion: @escaping (HKQuantity?) -> Void) {
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: false)
        let q = HKSampleQuery(sampleType: type, predicate: nil, limit: 1, sortDescriptors: [sort]) { _, samples, _ in
            completion((samples?.first as? HKQuantitySample)?.quantity)
        }
        store.execute(q)
    }
}
