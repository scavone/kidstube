import Foundation

/// Manages server credentials (URL + API key) persisted in the tvOS Keychain.
/// Used by Config to resolve credentials at runtime, replacing the build-time-only approach.
enum CredentialStore {
    private static let serverURLKey = "server_url"
    private static let apiKeyKey = "api_key"

    /// Whether valid credentials are stored (both URL and API key present).
    static var isPaired: Bool {
        serverURL != nil && apiKey != nil
    }

    /// The stored server base URL, or nil if not yet paired.
    static var serverURL: String? {
        KeychainService.read(key: serverURLKey)
    }

    /// The stored API key, or nil if not yet paired.
    static var apiKey: String? {
        KeychainService.read(key: apiKeyKey)
    }

    /// Store credentials after a successful pairing.
    @discardableResult
    static func store(serverURL: String, apiKey: String) -> Bool {
        // Normalize: strip trailing slash from server URL
        let normalizedURL = serverURL.hasSuffix("/")
            ? String(serverURL.dropLast())
            : serverURL

        let urlSaved = KeychainService.save(key: serverURLKey, value: normalizedURL)
        let keySaved = KeychainService.save(key: apiKeyKey, value: apiKey)
        return urlSaved && keySaved
    }

    /// Clear all stored credentials (unpair / forget server).
    static func clear() {
        KeychainService.delete(key: serverURLKey)
        KeychainService.delete(key: apiKeyKey)
    }
}
