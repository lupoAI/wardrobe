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
    // Optional fields present when the backend exposes thumbnail_status
    let thumbnailStatus: String?
    let hasCleanThumbnail: Bool?
    let backgroundRemoved: Bool?
    let thumbnailGeneratedAt: String?
    let thumbnailCleanedAt: String?

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
        case thumbnailStatus = "thumbnail_status"
        case hasCleanThumbnail = "has_clean_thumbnail"
        case backgroundRemoved = "background_removed"
        case thumbnailGeneratedAt = "thumbnail_generated_at"
        case thumbnailCleanedAt = "thumbnail_cleaned_at"
    }

    var displayTitle: String { notes?.isEmpty == false ? notes! : id }
    var subtitle: String { [category, subcategory].compactMap { $0 }.joined(separator: " / ") }

    enum ThumbnailState: Equatable {
        case cleanWithoutBG   // withoutBG-clean transparent thumbnail ready
        case legacyThumbnail  // older generated thumbnail exists, but not clean PNG
        case needsThumbnail   // no thumbnail yet; backend job has not produced one
        case originalFallback // no thumbnail data; showing original image fallback
    }

    // Prefers richer optional fields when present; falls back to has_thumbnail for older backends.
    var thumbnailState: ThumbnailState {
        if hasCleanThumbnail == true || backgroundRemoved == true || thumbnailStatus == "clean" {
            return .cleanWithoutBG
        }
        if thumbnailStatus == "legacy-jpg" || hasThumbnail == true {
            return .legacyThumbnail
        }
        if thumbnailStatus == "missing" || thumbnailStatus == "pending" || thumbnailStatus == "processing" {
            return .needsThumbnail
        }
        return .originalFallback
    }

    var thumbnailBadgeLabel: String {
        switch thumbnailState {
        case .cleanWithoutBG: return "withoutBG clean"
        case .legacyThumbnail: return "Legacy thumbnail"
        case .needsThumbnail: return "Thumbnail pending"
        case .originalFallback: return "Original fallback"
        }
    }

    var thumbnailStatusDescription: String {
        switch thumbnailState {
        case .cleanWithoutBG:
            return "Ready: backend created a transparent withoutBG-clean thumbnail."
        case .legacyThumbnail:
            return "A thumbnail exists, but it has not been refreshed through the withoutBG clean cutout flow yet."
        case .needsThumbnail:
            return "Waiting for the backend thumbnail job. Refresh after processing to see the withoutBG-clean version."
        case .originalFallback:
            return "Showing the original photo until the backend exposes thumbnail status."
        }
    }

    var thumbnailBadgeSystemImage: String {
        switch thumbnailState {
        case .cleanWithoutBG: return "sparkles"
        case .legacyThumbnail: return "photo.badge.checkmark"
        case .needsThumbnail: return "clock.badge.questionmark"
        case .originalFallback: return "photo"
        }
    }
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
