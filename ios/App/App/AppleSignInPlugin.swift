import AuthenticationServices
import Capacitor
import CryptoKit
import UIKit

/// Native Sign in with Apple bridge. Supabase receives the ID token and the
/// original nonce in the Web layer; no Apple credential is persisted here.
@objc(AppleSignInPlugin)
public class AppleSignInPlugin: CAPPlugin, CAPBridgedPlugin, ASAuthorizationControllerDelegate, ASAuthorizationControllerPresentationContextProviding {
    public let identifier = "AppleSignInPlugin"
    public let jsName = "AppleSignIn"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "signIn", returnType: CAPPluginReturnPromise)
    ]

    private var pendingCall: CAPPluginCall?
    private var rawNonce: String?
    private var authorizationController: ASAuthorizationController?
    private weak var presentationWindow: UIWindow?

    @objc func signIn(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            guard self.pendingCall == nil else {
                call.reject("Apple 登入正在進行中", "apple_sign_in_in_progress")
                return
            }
            guard let window = self.activeWindow() else {
                call.reject("找不到目前的 App 視窗", "apple_sign_in_window_unavailable")
                return
            }

            let nonce = UUID().uuidString
            let request = ASAuthorizationAppleIDProvider().createRequest()
            request.requestedScopes = [.fullName, .email]
            request.nonce = self.sha256(nonce)

            let controller = ASAuthorizationController(authorizationRequests: [request])
            controller.delegate = self
            controller.presentationContextProvider = self

            self.pendingCall = call
            self.rawNonce = nonce
            self.authorizationController = controller
            self.presentationWindow = window
            controller.performRequests()
        }
    }

    public func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {
        presentationWindow ?? activeWindow() ?? UIWindow()
    }

    public func authorizationController(controller: ASAuthorizationController, didCompleteWithAuthorization authorization: ASAuthorization) {
        guard let call = pendingCall, let nonce = rawNonce else {
            clearPendingRequest()
            return
        }
        guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
              let tokenData = credential.identityToken,
              let identityToken = String(data: tokenData, encoding: .utf8),
              !identityToken.isEmpty else {
            call.reject("Apple 沒有回傳可驗證的身分憑證", "apple_identity_token_missing")
            clearPendingRequest()
            return
        }

        var result: [String: Any] = [
            "state": "authorized",
            "identityToken": identityToken,
            "nonce": nonce
        ]
        if let name = credential.fullName {
            if let givenName = name.givenName { result["givenName"] = givenName }
            if let familyName = name.familyName { result["familyName"] = familyName }
            let fullName = PersonNameComponentsFormatter.localizedString(from: name, style: .default, options: [])
            if !fullName.isEmpty { result["fullName"] = fullName }
        }
        call.resolve(result)
        clearPendingRequest()
    }

    public func authorizationController(controller: ASAuthorizationController, didCompleteWithError error: Error) {
        guard let call = pendingCall else {
            clearPendingRequest()
            return
        }
        if let authError = error as? ASAuthorizationError, authError.code == .canceled {
            call.resolve(["state": "cancelled"])
        } else {
            call.reject(error.localizedDescription, appleErrorCode(error), error)
        }
        clearPendingRequest()
    }

    private func activeWindow() -> UIWindow? {
        UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .flatMap(\.windows)
            .first(where: \.isKeyWindow)
            ?? bridge?.viewController?.view.window
    }

    private func sha256(_ value: String) -> String {
        SHA256.hash(data: Data(value.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    private func appleErrorCode(_ error: Error) -> String {
        guard let authError = error as? ASAuthorizationError else { return "apple_sign_in_failed" }
        switch authError.code {
        case .invalidResponse: return "apple_invalid_response"
        case .notHandled: return "apple_not_handled"
        case .failed: return "apple_sign_in_failed"
        case .notInteractive: return "apple_not_interactive"
        case .matchedExcludedCredential: return "apple_credential_excluded"
        case .credentialImport: return "apple_credential_import_failed"
        case .credentialExport: return "apple_credential_export_failed"
        case .canceled: return "apple_sign_in_cancelled"
        @unknown default: return "apple_sign_in_failed"
        }
    }

    private func clearPendingRequest() {
        pendingCall = nil
        rawNonce = nil
        authorizationController = nil
        presentationWindow = nil
    }
}
