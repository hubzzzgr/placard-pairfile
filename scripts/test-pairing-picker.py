#!/usr/bin/env python3
"""Run the production UIKit picker/delegate and pairing store in an iOS simulator.

Uses synthetic credentials. Checks the copy-mode contract and callback-to-storage
handoff; tapping a file from a third-party Files provider still needs device QA.
"""
import json
import pathlib
import plistlib
import subprocess
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUNDLE_ID = "me.ssus.placard.picker-tests"


def run(*args):
    return subprocess.check_output(args, text=True).strip()


devices = json.loads(run("xcrun", "simctl", "list", "devices", "available", "--json"))["devices"]
device = next(d for runtime, items in devices.items() if "iOS-27" in runtime
              for d in items if d["name"].startswith("iPhone"))
udid = device["udid"]
if device["state"] != "Booted":
    run("xcrun", "simctl", "boot", udid)
run("xcrun", "simctl", "bootstatus", udid, "-b")

with tempfile.TemporaryDirectory(prefix="placard-picker-test-") as temporary:
    temporary = pathlib.Path(temporary)
    app = temporary / "PickerTests.app"
    app.mkdir()
    (app / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": BUNDLE_ID, "CFBundleName": "PickerTests",
        "CFBundleExecutable": "PickerTests", "CFBundlePackageType": "APPL",
        "CFBundleVersion": "1", "CFBundleShortVersionString": "1.0",
        "MinimumOSVersion": "27.0", "LSRequiresIPhoneOS": True,
        "UIDeviceFamily": [1], "UILaunchScreen": {},
    }))
    record = {"HostID": "test-host", "SystemBUID": "test-system"}
    record.update({key: b"synthetic-test-data" for key in [
        "DeviceCertificate", "HostCertificate", "HostPrivateKey", "RootCertificate", "RootPrivateKey",
    ]})
    (app / "fixture.plist").write_bytes(plistlib.dumps(record))
    main = temporary / "main.swift"
    main.write_text(r'''
import UIKit

@MainActor
final class PickerTestApp: UIResponder, UIApplicationDelegate {
    var window: UIWindow?

    func application(_ application: UIApplication, didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        let window = UIWindow(frame: UIScreen.main.bounds)
        window.rootViewController = UIViewController()
        window.makeKeyAndVisible()
        self.window = window
        DispatchQueue.main.async { self.testPicker() }
        return true
    }

    func testPicker() {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let result = documents.appendingPathComponent("result.txt")
        do {
            let source = Bundle.main.url(forResource: "fixture", withExtension: "plist")!
            var selections = 0
            var cancellations = 0
            var importError: Error?
            let view = PairingFilePicker(onPick: { url in
                selections += 1
                do {
                    _ = try PairingFileStore.save(Data(contentsOf: url), in: documents)
                } catch { importError = error }
            }, onCancel: { cancellations += 1 })
            let coordinator = view.makeCoordinator()
            let picker = view.makePicker(coordinator: coordinator)
            precondition(picker.documentPickerMode == .import, "Must copy rather than open in place")
            precondition(!picker.allowsMultipleSelection)
            precondition(picker.delegate === coordinator)
            coordinator.documentPicker(picker, didPickDocumentsAt: [source])
            if let importError { throw importError }
            precondition(selections == 1 && cancellations == 0)
            let saved = try Data(contentsOf: documents.appendingPathComponent("aircard_pairing.plist"))
            let original = try Data(contentsOf: source)
            precondition(saved == original, "Selection must reach durable storage")
            coordinator.documentPickerWasCancelled(picker)
            coordinator.documentPicker(picker, didPickDocumentsAt: [source])
            precondition(selections == 1 && cancellations == 0, "Complete once")

            for emptySelection in [false, true] {
                let cancelView = PairingFilePicker(onPick: { _ in
                    preconditionFailure("Cancellation must not import")
                }, onCancel: { cancellations += 1 })
                let delegate = cancelView.makeCoordinator()
                let controller = cancelView.makePicker(coordinator: delegate)
                if emptySelection {
                    delegate.documentPicker(controller, didPickDocumentsAt: [])
                } else {
                    delegate.documentPickerWasCancelled(controller)
                }
                delegate.documentPickerWasCancelled(controller)
            }
            precondition(cancellations == 2)
            try "PASS: UIKit copy-mode picker, selection-to-storage handoff, cancellation, single completion".write(to: result, atomically: true, encoding: .utf8)
        } catch {
            try? "FAIL: \(error)".write(to: result, atomically: true, encoding: .utf8)
        }
    }
}
UIApplicationMain(CommandLine.argc, CommandLine.unsafeArgv, nil, NSStringFromClass(PickerTestApp.self))
''', encoding="utf-8")
    sdk = run("xcrun", "--sdk", "iphonesimulator", "--show-sdk-path")
    subprocess.run([
        "xcrun", "swiftc", "-sdk", sdk, "-target", "arm64-apple-ios27.0-simulator",
        "-swift-version", "5", str(ROOT / "placard/Airlift/PairingFilePicker.swift"),
        str(ROOT / "placard/Airlift/PairingFileStore.swift"), str(main),
        "-o", str(app / "PickerTests"),
    ], check=True)
    run("codesign", "--force", "--sign", "-", str(app))
    run("xcrun", "simctl", "install", udid, str(app))
    container = pathlib.Path(run("xcrun", "simctl", "get_app_container", udid, BUNDLE_ID, "data"))
    result = container / "Documents/result.txt"
    result.unlink(missing_ok=True)
    run("xcrun", "simctl", "launch", "--terminate-running-process", udid, BUNDLE_ID)
    for _ in range(60):
        if result.exists():
            message = result.read_text()
            print(message)
            if not message.startswith("PASS:"):
                raise RuntimeError(message)
            break
        time.sleep(1)
    else:
        raise RuntimeError("Picker simulator test did not complete")
