import SwiftUI
import Network
import Combine
import UniformTypeIdentifiers

@MainActor
final class AirliftWiFiMonitor: ObservableObject {
    enum Status {
        case checking
        case connected
        case disconnected
    }

    @Published private(set) var status: Status = .checking

    private let monitor = NWPathMonitor(requiredInterfaceType: .wifi)
    private let queue = DispatchQueue(label: "me.ssus.placard.airlift.wifi-monitor")

    init() {
        monitor.pathUpdateHandler = { [weak self] path in
            let status: Status = path.status == .satisfied ? .connected : .disconnected
            DispatchQueue.main.async {
                self?.status = status
            }
        }
        monitor.start(queue: queue)
    }

    deinit {
        monitor.cancel()
    }
}

/// Connects the existing setup screens to AirCard's on-device pairing host.
struct AirliftEntryView: View {
    @ObservedObject private var pairing = PairingController.shared
    @StateObject private var wifiMonitor = AirliftWiFiMonitor()
    @State private var paired = FileManager.default.fileExists(atPath: PairingController.pairingFilePath())
    @State private var connected = false
    @State private var checking = false
    @State private var pairingError: String?
    @State private var connectionError: String?
    @State private var importingPairingFile = false

    var body: some View {
        setupView
            .fileImporter(
                isPresented: $importingPairingFile,
                // Pairing files often have unregistered extensions in Files.
                allowedContentTypes: [.item],
                allowsMultipleSelection: false,
                onCompletion: importPairingFile
            )
    }

    @ViewBuilder
    private var setupView: some View {
        switch wifiMonitor.status {
        case .checking:
            AirliftWiFiCheckingView()
        case .disconnected:
            AirliftWiFiRequiredView()
        case .connected:
            if connected {
                PlacardRootView()
            } else if paired {
                AirliftVPNView(
                    connectionError: connectionError, checking: checking,
                    onCheck: checkConnection,
                    onPairAgain: {
                        paired = false
                        pairingError = nil
                        connectionError = nil
                    }
                )
            } else {
                AirliftPairingView(
                    running: pairing.running, pin: pairing.pairingPIN,
                    error: pairingError, onStart: startPairing,
                    onImport: {
                        pairingError = nil
                        importingPairingFile = true
                    }
                )
            }
        }
    }

    private func importPairingFile(_ result: Result<[URL], Error>) {
        do {
            guard let url = try result.get().first else { return }
            try pairing.importPairingFile(from: url)
            pairingError = nil
            connectionError = nil
            paired = true
        } catch {
            pairingError = error.localizedDescription
        }
    }

    private func startPairing() {
        guard !pairing.running else { return }
        pairingError = nil
        Task {
            do {
                _ = try await pairing.startAndWait()
                paired = true
            } catch {
                pairingError = error.localizedDescription
            }
        }
    }

    private func checkConnection() {
        guard !checking else { return }
        checking = true
        connectionError = nil
        Task {
            defer { checking = false }
            do {
                _ = try await TendiesEngine.shared.detectPosterBoardContainer(
                    pairingPath: PairingController.pairingFilePath()
                )
                connected = true
            } catch {
                connectionError = error.localizedDescription
            }
        }
    }
}
