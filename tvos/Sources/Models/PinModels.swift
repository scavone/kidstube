import Foundation

/// Response from GET /api/children/{id}/pin-status — whether PIN lock is enabled for this child.
struct PinStatusResponse: Codable {
    let pinEnabled: Bool

    enum CodingKeys: String, CodingKey {
        case pinEnabled = "pin_enabled"
    }
}

/// Response from POST /api/children/{id}/verify-pin — whether the entered PIN was correct.
struct PinVerifyResponse: Codable {
    let success: Bool
    let sessionToken: String?

    enum CodingKeys: String, CodingKey {
        case success
        case sessionToken = "session_token"
    }
}
