import SwiftUI
#if canImport(PhotosUI)
import PhotosUI
#endif

@main
struct WardrobeApp: App {
    @StateObject private var settings = AppSettings()

    var body: some Scene {
        WindowGroup {
            NavigationStack {
                ItemGridView()
            }
            .environmentObject(settings)
        }
    }
}

struct ItemGridView: View {
    @EnvironmentObject private var settings: AppSettings
    @State private var items: [WardrobeItem] = []
    @State private var selectedCategory: WardrobeCategory = .all
    @State private var searchText = ""
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var showingSettings = false
    @State private var showingUpload = false

    private let columns = [GridItem(.adaptive(minimum: 150), spacing: 16)]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Picker("Category", selection: $selectedCategory) {
                    ForEach(WardrobeCategory.allCases) { category in
                        Text(category.title).tag(category)
                    }
                }
                .pickerStyle(.segmented)
                .padding(.horizontal)

                if let errorMessage {
                    ContentUnavailableView("Could not load wardrobe", systemImage: "wifi.exclamationmark", description: Text(errorMessage))
                        .padding(.horizontal)
                } else if isLoading && items.isEmpty {
                    ProgressView("Loading wardrobe…")
                        .frame(maxWidth: .infinity, minHeight: 240)
                } else if items.isEmpty {
                    ContentUnavailableView("No items", systemImage: "tshirt", description: Text("Upload a piece or adjust filters."))
                        .padding(.top, 80)
                }

                LazyVGrid(columns: columns, spacing: 16) {
                    ForEach(items) { item in
                        NavigationLink(value: item) {
                            ItemCard(item: item, api: api)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal)
            }
            .padding(.vertical)
        }
        .navigationTitle("Wardrobe")
        .searchable(text: $searchText, prompt: "Color, tag, item id…")
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button { showingUpload = true } label: { Label("Upload", systemImage: "plus") }
                Button { showingSettings = true } label: { Label("Settings", systemImage: "gear") }
            }
        }
        .refreshable { await loadItems() }
        .task { await loadItems() }
        .onChange(of: selectedCategory) { _, _ in Task { await loadItems() } }
        .onSubmit(of: .search) { Task { await loadItems() } }
        .navigationDestination(for: WardrobeItem.self) { item in
            ItemDetailView(item: item, api: api)
        }
        .sheet(isPresented: $showingSettings) { SettingsView().environmentObject(settings) }
        .sheet(isPresented: $showingUpload, onDismiss: { Task { await loadItems() } }) {
            UploadView(api: api)
        }
    }

    private var api: WardrobeAPI {
        WardrobeAPI(baseURL: settings.baseURL ?? URL(string: "http://192.168.8.140:8765")!)
    }

    private func loadItems() async {
        guard let baseURL = settings.baseURL else {
            errorMessage = APIError.missingBaseURL.localizedDescription
            return
        }
        isLoading = true
        defer { isLoading = false }
        do {
            items = try await WardrobeAPI(baseURL: baseURL).items(category: selectedCategory, query: searchText)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct ItemCard: View {
    let item: WardrobeItem
    let api: WardrobeAPI

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            AsyncImage(url: api.resolvedImageURL(item.thumbnailURL ?? item.imageURL)) { phase in
                switch phase {
                case let .success(image): image.resizable().scaledToFill()
                case .failure: Image(systemName: "photo").font(.largeTitle).foregroundStyle(.secondary)
                default: ProgressView()
                }
            }
            .frame(height: 190)
            .frame(maxWidth: .infinity)
            .background(.thinMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 22))
            .overlay(alignment: .topTrailing) {
                ThumbnailBadge(state: item.thumbnailState)
                    .padding(8)
            }

            Text(item.displayTitle)
                .font(.headline)
                .lineLimit(2)
            Text(item.subtitle)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            TagRow(values: Array(item.colors.prefix(3)), style: .color)
        }
        .padding(12)
        .background(.background.secondary, in: RoundedRectangle(cornerRadius: 28))
    }
}

struct ItemDetailView: View {
    let item: WardrobeItem
    let api: WardrobeAPI

    var body: some View {
        List {
            AsyncImage(url: api.resolvedImageURL(item.originalImageURL ?? item.imageURL)) { phase in
                switch phase {
                case let .success(image): image.resizable().scaledToFit()
                case .failure: ContentUnavailableView("Image unavailable", systemImage: "photo")
                default: ProgressView()
                }
            }
            .listRowInsets(EdgeInsets())
            .frame(maxWidth: .infinity)
            .background(Color.secondary.opacity(0.12))

            Section("Details") {
                LabeledContent("ID", value: item.id)
                LabeledContent("Category", value: item.subtitle)
                if let original = item.originalFilename { LabeledContent("Original", value: original) }
                if let created = item.createdAt { LabeledContent("Created", value: created) }
                LabeledContent("Thumbnail") {
                    Label(item.thumbnailBadgeLabel, systemImage: item.thumbnailBadgeSystemImage)
                        .font(.subheadline)
                        .foregroundStyle(item.thumbnailState == .cleanWithoutBG ? .green : .secondary)
                }
                Text(item.thumbnailStatusDescription)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                if let generated = item.thumbnailGeneratedAt { LabeledContent("Generated", value: generated) }
                if let cleaned = item.thumbnailCleanedAt { LabeledContent("Cleaned", value: cleaned) }
            }

            if !item.colors.isEmpty {
                Section("Colors") { TagRow(values: item.colors, style: .color) }
            }
            if !item.tags.isEmpty {
                Section("Tags") { TagRow(values: item.tags, style: .plain) }
            }
        }
        .navigationTitle(item.displayTitle)
    }
}

struct TagRow: View {
    enum Style { case color, plain }
    let values: [String]
    let style: Style

    var body: some View {
        FlowLayout(spacing: 8) {
            ForEach(values, id: \.self) { value in
                Text(value)
                    .font(.caption.weight(.bold))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(style == .color ? Color.orange.opacity(0.18) : Color.secondary.opacity(0.12), in: Capsule())
            }
        }
    }
}

struct ThumbnailBadge: View {
    let state: WardrobeItem.ThumbnailState

    var body: some View {
        Label(label, systemImage: systemImage)
            .font(.caption2.weight(.bold))
            .labelStyle(.titleAndIcon)
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .foregroundStyle(foregroundStyle)
            .background(backgroundStyle, in: Capsule())
            .accessibilityLabel(label)
    }

    private var label: String {
        switch state {
        case .cleanWithoutBG: return "withoutBG"
        case .legacyThumbnail: return "Legacy"
        case .needsThumbnail: return "Pending"
        case .originalFallback: return "Original"
        }
    }

    private var systemImage: String {
        switch state {
        case .cleanWithoutBG: return "sparkles"
        case .legacyThumbnail: return "photo.badge.checkmark"
        case .needsThumbnail: return "clock"
        case .originalFallback: return "photo"
        }
    }

    private var foregroundStyle: Color {
        switch state {
        case .cleanWithoutBG: return .green
        case .legacyThumbnail: return .orange
        case .needsThumbnail, .originalFallback: return .secondary
        }
    }

    private var backgroundStyle: Color {
        switch state {
        case .cleanWithoutBG: return .green.opacity(0.16)
        case .legacyThumbnail: return .orange.opacity(0.16)
        case .needsThumbnail, .originalFallback: return .secondary.opacity(0.14)
        }
    }
}

struct SettingsView: View {
    @EnvironmentObject private var settings: AppSettings
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Backend") {
                    TextField("http://192.168.8.140:8765", text: $settings.baseURLString)
                    Text("Use this Mac's LAN URL for a physical iPhone, or 127.0.0.1 for the simulator.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                Section("Thumbnail workflow") {
                    Text("The backend generates transparent withoutBG-clean thumbnails for uploaded and imported items. New items may show the original photo first; refresh after the thumbnail job has run.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Settings")
            .toolbar { Button("Done") { dismiss() } }
        }
    }
}

struct UploadView: View {
    let api: WardrobeAPI
    @Environment(\.dismiss) private var dismiss
    @State private var category: WardrobeCategory = .tops
    @State private var notes = ""
    @State private var imageData: Data?
    @State private var selectedImage: Image?
    @State private var isUploading = false
    @State private var errorMessage: String?
    #if canImport(PhotosUI)
    @State private var pickerItem: PhotosPickerItem?
    #endif

    var body: some View {
        NavigationStack {
            Form {
                Section("Photo") {
                    selectedImage?
                        .resizable()
                        .scaledToFit()
                        .frame(maxHeight: 260)
                    #if canImport(PhotosUI)
                    PhotosPicker(selection: $pickerItem, matching: .images) {
                        Label(imageData == nil ? "Choose photo" : "Change photo", systemImage: "photo.on.rectangle")
                    }
                    #else
                    Text("Photo picker is available on iOS builds.")
                    #endif
                }
                Section("Metadata") {
                    Picker("Category", selection: $category) {
                        ForEach(WardrobeCategory.allCases.filter { $0 != .all }) { category in
                            Text(category.title).tag(category)
                        }
                    }
                    TextField("Notes", text: $notes, axis: .vertical)
                }
                Section("After upload") {
                    Text("The backend stores the original photo immediately, then its thumbnail workflow creates a transparent withoutBG-clean catalog icon. If this item appears as an original fallback, refresh the grid after processing finishes.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                if let errorMessage { Section { Text(errorMessage).foregroundStyle(.red) } }
            }
            .navigationTitle("Upload item")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(isUploading ? "Uploading…" : "Upload") { Task { await upload() } }
                        .disabled(imageData == nil || isUploading)
                }
            }
            #if canImport(PhotosUI)
            .onChange(of: pickerItem) { _, newItem in Task { await loadTransferableImage(from: newItem) } }
            #endif
        }
    }

    #if canImport(PhotosUI)
    private func loadTransferableImage(from item: PhotosPickerItem?) async {
        guard let item else { return }
        do {
            if let data = try await item.loadTransferable(type: Data.self) {
                imageData = data
                #if canImport(UIKit)
                if let uiImage = UIImage(data: data) { selectedImage = Image(uiImage: uiImage) }
                #endif
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
    #endif

    private func upload() async {
        guard let imageData else { return }
        isUploading = true
        defer { isUploading = false }
        do {
            _ = try await api.upload(imageData: imageData, filename: "ios-upload.jpg", category: category, notes: notes)
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        arrange(proposal: proposal, subviews: subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        for row in arrange(proposal: proposal, subviews: subviews).rows {
            for element in row.elements {
                element.subview.place(at: CGPoint(x: bounds.minX + element.x, y: bounds.minY + row.y), proposal: .unspecified)
            }
        }
    }

    private func arrange(proposal: ProposedViewSize, subviews: Subviews) -> (rows: [Row], size: CGSize) {
        let maxWidth = proposal.width ?? 320
        var rows: [Row] = [Row(y: 0, height: 0, elements: [])]
        var x: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > 0, x + size.width > maxWidth {
                let previousHeight = rows[rows.count - 1].height
                rows.append(Row(y: rows[rows.count - 1].y + previousHeight + spacing, height: 0, elements: []))
                x = 0
            }
            rows[rows.count - 1].elements.append(Element(subview: subview, x: x))
            rows[rows.count - 1].height = max(rows[rows.count - 1].height, size.height)
            x += size.width + spacing
        }
        let height = (rows.last?.y ?? 0) + (rows.last?.height ?? 0)
        return (rows, CGSize(width: maxWidth, height: height))
    }

    struct Row { var y: CGFloat; var height: CGFloat; var elements: [Element] }
    struct Element { let subview: LayoutSubview; let x: CGFloat }
}
