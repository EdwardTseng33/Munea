import Capacitor
import GoogleSignIn
import UIKit

/// Native Google Sign-In bridge. Google handles account selection and returns
/// an ID token; Supabase exchanges that token for the normal Munea session.
@objc(GoogleSignInPlugin)
public class GoogleSignInPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "GoogleSignInPlugin"
    public let jsName = "GoogleSignIn"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "signIn", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "signOut", returnType: CAPPluginReturnPromise)
    ]

    private var pendingCall: CAPPluginCall?

    @objc func signIn(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            guard self.pendingCall == nil else {
                call.reject("Google 登入正在進行中", "google_sign_in_in_progress")
                return
            }
            guard let presenter = self.bridge?.viewController else {
                call.reject("找不到目前的 App 畫面", "google_sign_in_view_unavailable")
                return
            }
            guard let clientID = self.infoValue("GIDClientID"), self.validClientID(clientID) else {
                call.reject("尚未設定 Google iOS Client ID", "google_ios_client_id_missing")
                return
            }

            let serverClientID = self.infoValue("GIDServerClientID").flatMap {
                self.validClientID($0) ? $0 : nil
            }
            GIDSignIn.sharedInstance.configuration = GIDConfiguration(
                clientID: clientID,
                serverClientID: serverClientID
            )

            self.pendingCall = call
            GIDSignIn.sharedInstance.signIn(withPresenting: presenter) { result, error in
                guard let pendingCall = self.pendingCall else { return }
                defer { self.pendingCall = nil }

                if let error = error as NSError? {
                    if error.domain == kGIDSignInErrorDomain && error.code == -5 {
                        pendingCall.resolve(["state": "cancelled"])
                    } else {
                        pendingCall.reject(error.localizedDescription, "google_sign_in_failed", error)
                    }
                    return
                }
                guard let user = result?.user,
                      let idToken = user.idToken?.tokenString,
                      !idToken.isEmpty else {
                    pendingCall.reject("Google 沒有回傳可驗證的身分憑證", "google_identity_token_missing")
                    return
                }

                var payload: [String: Any] = [
                    "state": "authorized",
                    "identityToken": idToken
                ]
                if let email = user.profile?.email, !email.isEmpty { payload["email"] = email }
                if let name = user.profile?.name, !name.isEmpty { payload["fullName"] = name }
                if let givenName = user.profile?.givenName, !givenName.isEmpty { payload["givenName"] = givenName }
                if let familyName = user.profile?.familyName, !familyName.isEmpty { payload["familyName"] = familyName }
                if let avatarURL = user.profile?.imageURL(withDimension: 256)?.absoluteString {
                    payload["avatarUrl"] = avatarURL
                }
                pendingCall.resolve(payload)
            }
        }
    }

    @objc func signOut(_ call: CAPPluginCall) {
        GIDSignIn.sharedInstance.signOut()
        call.resolve(["ok": true])
    }

    private func infoValue(_ key: String) -> String? {
        (Bundle.main.object(forInfoDictionaryKey: key) as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func validClientID(_ value: String) -> Bool {
        value.hasSuffix(".apps.googleusercontent.com") && !value.contains("MISSING_")
    }
}
