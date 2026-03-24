import Foundation

/// Response from POST /api/pair/request — contains the pairing token, PIN, and expiration.
struct PairRequestResponse: Codable {
    let token: String
    let pin: String
    let expiresAt: String
    let expiresIn: Int

    enum CodingKeys: String, CodingKey {
        case token, pin
        case expiresAt = "expires_at"
        case expiresIn = "expires_in"
    }
}

/// Response from GET /api/pair/status/{token} — poll until confirmed, expired, or denied.
struct PairStatusResponse: Codable {
    let status: String
    let apiKey: String?
    let serverUrl: String?

    enum CodingKeys: String, CodingKey {
        case status
        case apiKey = "api_key"
        case serverUrl = "server_url"
    }

    var isPending: Bool { status == "pending" }
    var isConfirmed: Bool { status == "confirmed" }
    var isExpired: Bool { status == "expired" }
    var isDenied: Bool { status == "denied" }
}
