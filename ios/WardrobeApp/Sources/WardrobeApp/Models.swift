import Foundation

struct WardrobeItem: Identifiable, Codable, Hashable {
    let id: String
    let originalFilename: String?
    let imagePath: String?
    let embeddingPath: String?
    let category: String
    let subcategory: String?
    let colors: [String]
    let tags: [String]
    let notes: String?
    let createdAt: String?
    let imageURL: String?
    let originalImageURL: String?
    let thumbnailURL: String?
    let hasThumbnail: Bool?

    enum CodingKeys: String, CodingKey {
        case id
        case originalFilename = "original_filename"
        case imagePath = "image_path"
        case embeddingPath = "embedding_path"
        case category, subcategory, colors, tags, notes
        case createdAt = "created_at"
        case imageURL = "image_url"
        case originalImageURL = "original_image_url"
        case thumbnailURL = "thumbnail_url"
        case hasThumbnail = "has_thumbnail"
    }

    var displayTitle: String { notes?.isEmpty == false ? notes! : id }
    var subtitle: String { [category, subcategory].compactMap { $0 }.joined(separator: " / ") }
}

struct UploadItemRequest: Encodable {
    let filename: String
    let imageBase64: String
    let category: String?
    let notes: String?

    enum CodingKeys: String, CodingKey {
        case filename
        case imageBase64 = "image_base64"
        case category
        case notes
    }
}

enum WardrobeCategory: String, CaseIterable, Identifiable {
    case all = ""
    case tops, bottoms, outerwear, shoes, accessories, underwear, unknown

    var id: String { rawValue }
    var title: String { self == .all ? "All" : rawValue.capitalized }
}
