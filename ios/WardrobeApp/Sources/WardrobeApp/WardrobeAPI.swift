import Foundation

@MainActor
final class AppSettings: ObservableObject {
    @Published var baseURLString: String {
        didSet { UserDefaults.standard.set(baseURLString, forKey: Self.baseURLKey) }
    }

    private static let baseURLKey = "WardrobeBackendBaseURL"

    init() {
        baseURLString = UserDefaults.standard.string(forKey: Self.baseURLKey) ?? "http://127.0.0.1:8765"
    }

    var baseURL: URL? { URL(string: baseURLString.trimmingCharacters(in: .whitespacesAndNewlines)) }
}

struct WardrobeAPI {
    var baseURL: URL
    var session: URLSession = .shared

    func items(category: WardrobeCategory = .all, query: String = "") async throws -> [WardrobeItem] {
        var components = URLComponents(url: baseURL.appending(path: "api/items"), resolvingAgainstBaseURL: false)!
        var queryItems: [URLQueryItem] = []
        if category != .all { queryItems.append(URLQueryItem(name: "category", value: category.rawValue)) }
        if !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { queryItems.append(URLQueryItem(name: "q", value: query)) }
        components.queryItems = queryItems.isEmpty ? nil : queryItems
        return try await decode([WardrobeItem].self, from: components.url!)
    }

    func item(id: String) async throws -> WardrobeItem {
        try await decode(WardrobeItem.self, from: baseURL.appending(path: "api/items/\(id)"))
    }

    func upload(imageData: Data, filename: String, category: WardrobeCategory, notes: String) async throws -> WardrobeItem {
        let requestBody = UploadItemRequest(
            filename: filename,
            imageBase64: imageData.base64EncodedString(),
            category: category == .all ? nil : category.rawValue,
            notes: notes.isEmpty ? nil : notes
        )
        var request = URLRequest(url: baseURL.appending(path: "api/items"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(requestBody)
        return try await decode(WardrobeItem.self, for: request)
    }

    func resolvedImageURL(_ path: String?) -> URL? {
        guard let path else { return nil }
        if let absolute = URL(string: path), absolute.scheme != nil { return absolute }
        return URL(string: path, relativeTo: baseURL)?.absoluteURL
    }

    private func decode<T: Decodable>(_ type: T.Type, from url: URL) async throws -> T {
        try await decode(type, for: URLRequest(url: url))
    }

    private func decode<T: Decodable>(_ type: T.Type, for request: URLRequest) async throws -> T {
        let (data, response) = try await session.data(for: request)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw APIError.httpStatus(http.statusCode, body)
        }
        return try JSONDecoder().decode(T.self, from: data)
    }
}

enum APIError: LocalizedError {
    case missingBaseURL
    case httpStatus(Int, String)

    var errorDescription: String? {
        switch self {
        case .missingBaseURL:
            return "Set a valid backend URL first."
        case let .httpStatus(status, body):
            return "Backend returned HTTP \(status). \(body)"
        }
    }
}
