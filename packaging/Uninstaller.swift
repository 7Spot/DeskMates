// Runs from a private temporary directory, outside the application being recycled.
// A ready -> commit -> parent exit handshake keeps preparation non-destructive.
import AppKit
import Darwin

private let appID = "com.deskmate.companion"
private let preferencesID = "com.deskmate.Companion"
private let fm = FileManager.default

private func resolved(_ url: URL) -> URL {
    // Foundation standardization can shorten /private/tmp back to /tmp. Use the
    // filesystem's canonical spelling, matching Python Path.resolve and stat.
    var path = [CChar](repeating: 0, count: Int(PATH_MAX))
    return realpath(url.path, &path) == nil ? url : URL(fileURLWithPath: String(cString: path))
}

private struct Request: Decodable {
    let pid: Int32
    let language: String
    let bundle: String
    let device: UInt64
    let inode: UInt64
    let executable: String
#if UNINSTALL_TESTING
    let testDataRoot: String
#endif
}

private struct Failure: Error { let message: String }

private final class Uninstaller: NSObject, NSApplicationDelegate {
    let folder: URL
    let request: Request
    let panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 430, height: 192),
                        styleMask: [.titled], backing: .buffered, defer: false)
    let label = NSTextField(wrappingLabelWithString: "")
    let spinner = NSProgressIndicator()
    let retry = NSButton(title: "", target: nil, action: nil)
    let finder = NSButton(title: "", target: nil, action: nil)
    let close = NSButton(title: "", target: nil, action: nil)
    var timer: Timer?
    var began = Date()
    var committedAt: Date?
    var busy = false
    var canAbandonRecycle = false
    var abandoned = false
    var recycleAttempt = 0
    var recycled = false
    var recycledURL: URL?
    var finished = false

    init(folder: URL, request: Request) {
        self.folder = folder
        self.request = request
        super.init()
    }

    func tr(_ en: String, _ zh: String) -> String { request.language == "zh" ? zh : en }
    var target: URL? { request.bundle.isEmpty ? nil : URL(fileURLWithPath: request.bundle) }
    var parentAlive: Bool { kill(request.pid, 0) == 0 || errno == EPERM }
    var anotherAppRunning: Bool {
#if UNINSTALL_TESTING
        return false // A test helper never cleans the real user's data.
#else
        return !NSRunningApplication.runningApplications(withBundleIdentifier: appID).isEmpty
#endif
    }

    func report(_ state: String, code: String = "", message: String = "") throws {
        let data = try JSONSerialization.data(withJSONObject: ["state": state, "code": code, "message": message, "trash": recycledURL?.path ?? ""])
        try data.write(to: folder.appendingPathComponent("status.json"), options: .atomic)
    }

    func validateTarget(checkProcess: Bool) throws {
        guard request.pid > 1, request.pid != getpid() else {
            throw Failure(message: tr("The running app could not be verified", "无法确认当前应用的身份"))
        }
        guard let url = target else { return } // Source mode has no application target.
        let real = resolved(url)
        let infoURL = real.appendingPathComponent("Contents/Info.plist")
        guard real.path == url.path, url.pathExtension == "app",
              let info = NSDictionary(contentsOf: infoURL), info["CFBundleIdentifier"] as? String == appID,
              let executable = info["CFBundleExecutable"] as? String,
              !executable.isEmpty, (executable as NSString).lastPathComponent == executable,
              resolved(real.appendingPathComponent("Contents/MacOS/" + executable)).path == request.executable else {
            throw Failure(message: tr("The running app could not be verified", "无法确认当前应用的身份"))
        }
        var details = stat()
        guard stat(real.path, &details) == 0,
              UInt64(details.st_dev) == request.device, UInt64(details.st_ino) == request.inode else {
            throw Failure(message: tr("The application changed. Open it again before uninstalling.", "应用位置或内容已变化，请重新打开后再卸载。"))
        }
        let volume = try real.resourceValues(forKeys: [.volumeIsReadOnlyKey])
        guard volume.volumeIsReadOnly != true else {
            throw Failure(message: tr("Move the app to Applications before uninstalling", "请先将应用移到“应用程序”文件夹，再卸载"))
        }
        if checkProcess {
            var path = [CChar](repeating: 0, count: 4096)
            guard proc_pidpath(request.pid, &path, UInt32(path.count)) > 0,
                  resolved(URL(fileURLWithPath: String(cString: path))).path == request.executable else {
                throw Failure(message: tr("The running app could not be verified", "无法确认当前应用的身份"))
            }
        }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        panel.title = tr("Uninstall DeskMates", "卸载同桌")
        panel.isReleasedWhenClosed = false
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.hidesOnDeactivate = false
        let view = panel.contentView!
        label.frame = NSRect(x: 24, y: 76, width: 382, height: 84)
        label.font = .systemFont(ofSize: 14)
        label.maximumNumberOfLines = 5
        view.addSubview(label)
        spinner.frame = NSRect(x: 24, y: 29, width: 18, height: 18)
        spinner.style = .spinning
        spinner.controlSize = .small
        view.addSubview(spinner)
        for (button, x, width, title, action) in [
            (retry, 24.0, 90.0, tr("Retry", "重试"), #selector(retryAction)),
            (finder, 119.0, 163.0, tr("Show in Finder", "在访达中显示"), #selector(finderAction)),
            (close, 302.0, 104.0, tr("Close", "关闭"), #selector(closeAction))
        ] {
            button.frame = NSRect(x: x, y: 20, width: width, height: 34)
            button.title = title
            button.bezelStyle = .rounded
            button.target = self
            button.action = action
            button.isHidden = true
            view.addSubview(button)
        }
        label.stringValue = tr("Preparing to uninstall…", "正在准备卸载…")
        spinner.startAnimation(nil)
        panel.center()
        panel.orderFrontRegardless()
        // This runs on the AppKit event loop, after the independent panel exists.
        DispatchQueue.main.async { [self] in
            do {
                guard parentAlive else { throw Failure(message: tr("The app already quit. Please try again.", "应用已退出，请重新打开后再试。")) }
                try validateTarget(checkProcess: true)
                panel.displayIfNeeded()
                try report("ready")
                timer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in self?.poll() }
            } catch { fail(error, retryable: false) }
        }
    }

    func poll() {
        if fm.fileExists(atPath: folder.appendingPathComponent("cancel").path) {
            try? report("cancelled")
            NSApp.terminate(nil)
            return
        }
        if committedAt == nil {
            if fm.fileExists(atPath: folder.appendingPathComponent("commit.json").path) {
                committedAt = Date()
                label.stringValue = tr("Waiting for DeskMates to close…", "正在等待同桌退出…")
                try? report("waiting")
            } else if Date().timeIntervalSince(began) > 30 || !parentAlive {
                fail(Failure(message: tr("Uninstall was not started. Your app and data were kept.", "卸载未开始，应用和数据已保留。")), retryable: false)
            }
            return
        }
        if !parentAlive {
            timer?.invalidate()
            performUninstall()
        } else if Date().timeIntervalSince(committedAt!) > 20 {
            fail(Failure(message: tr("DeskMates has not closed. Your app and data were kept.", "同桌尚未退出，应用和数据已保留。")), retryable: true)
        }
    }

    func performUninstall() {
        guard !busy else { return }
        guard !parentAlive, !anotherAppRunning else {
            fail(Failure(message: tr("Close all DeskMates windows, then retry. Your data were kept.", "请退出所有同桌实例后重试，数据已保留。")), retryable: true)
            return
        }
        retry.isHidden = true; finder.isHidden = true; close.isHidden = true
        spinner.isHidden = false; spinner.startAnimation(nil)
        if recycled || target == nil { cleanData(); return }
        do { try validateTarget(checkProcess: false) }
        catch { fail(error, retryable: true); return }
        busy = true
        canAbandonRecycle = false
        recycleAttempt += 1
        let attempt = recycleAttempt
        label.stringValue = tr("Moving the app to Trash…\nmacOS may ask for permission.", "正在将应用移到废纸篓…\nmacOS 可能会请求授权。")
        try? report("recycling")
        let url = target!
        NSWorkspace.shared.recycle([url]) { [weak self] moved, error in
            DispatchQueue.main.async {
                guard let self = self, !self.abandoned else { return }
                self.busy = false
                guard error == nil, moved[url] != nil else {
                    let detail = error?.localizedDescription ?? self.tr("macOS did not confirm moving the app to Trash.", "macOS 未确认应用已移到废纸篓。")
                    self.fail(Failure(message: detail + "\n" + self.tr("Your settings and data were kept.", "设置和数据已保留。")), retryable: true)
                    return
                }
                self.recycled = true
                self.recycledURL = moved[url]
                self.cleanData()
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 120) { [weak self] in
            guard let self = self, self.busy, self.recycleAttempt == attempt else { return }
            // The native operation cannot safely be retried while its result is unknown.
            self.canAbandonRecycle = true
            self.close.title = self.tr("Stop waiting", "停止等待")
            self.close.isHidden = false
            self.label.stringValue = self.tr("Still waiting for macOS. You can stop waiting and keep your data. macOS may still move the app to Trash.", "仍在等待 macOS。停止等待会保留数据；系统仍可能稍后将应用移到废纸篓。")
        }
    }

    func cleanData() {
        // Permission prompts can outlive the parent process. Another copy may
        // have been opened while the system was recycling the original bundle.
        guard !parentAlive, !anotherAppRunning else {
            fail(Failure(message: tr("DeskMates was opened again. Close it before clearing data. Your data were kept.", "同桌已重新打开，请退出后再清理。数据已保留。")), retryable: true, partial: recycled)
            return
        }
        // The list is compiled in. No path, preference domain or home directory is
        // accepted from the request, and symlinked parent directories are refused.
#if UNINSTALL_TESTING
        let home = resolved(URL(fileURLWithPath: request.testDataRoot))
#else
        let home = resolved(fm.homeDirectoryForCurrentUser)
#endif
        let paths = ["Library/Preferences/" + preferencesID + ".plist", "Library/Logs/Deskmate.log", "Library/Caches/Deskmate"]
        var problems: [String] = []
        for path in paths {
            let url = home.appendingPathComponent(path)
            let parent = url.deletingLastPathComponent()
            guard resolved(parent).path == parent.path else {
                problems.append(path); continue
            }
            do {
                var entry = stat()
                let found = lstat(url.path, &entry) == 0
                if !found && errno != ENOENT { throw Failure(message: path) }
                if path.hasPrefix("Library/Preferences/") {
                    if found && entry.st_mode & S_IFMT == S_IFLNK { throw Failure(message: path) }
#if !UNINSTALL_TESTING
                    let preferences = UserDefaults(suiteName: preferencesID)!
                    preferences.removePersistentDomain(forName: preferencesID)
                    guard preferences.synchronize() else { throw Failure(message: path) }
#endif
                }
                // removeItem removes a link itself, never its destination.
                // Preferences synchronization may already have removed its plist.
                // Missing is success; permission and all other errors still count.
                do { try fm.removeItem(at: url) }
                catch let error as NSError {
                    let missing = (error.domain == NSCocoaErrorDomain && error.code == NSFileNoSuchFileError)
                        || (error.domain == NSPOSIXErrorDomain && error.code == Int(ENOENT))
                    if !missing { throw error }
                }
            } catch { problems.append(path) }
        }
        if !problems.isEmpty {
            let intro = recycled ? tr("The app was removed, but some data could not be cleared:\n", "应用已移到废纸篓，但部分数据未能清理：\n") : tr("Some settings or data could not be cleared:\n", "部分设置或数据未能清理：\n")
            fail(Failure(message: intro + problems.joined(separator: "\n")), retryable: true, partial: true)
            return
        }
        finished = true
        spinner.stopAnimation(nil); spinner.isHidden = true
        label.stringValue = target == nil ? tr("Settings and data removed. Source files were kept.", "设置和数据已删除，源码文件已保留。") : tr("The app was moved to Trash. Settings and data were removed.", "应用已移到废纸篓，设置和数据已删除。")
        close.isHidden = false
        close.title = tr("Close", "关闭")
        try? report("done")
    }

    func fail(_ error: Error, retryable: Bool, partial: Bool = false) {
        timer?.invalidate()
        busy = false
        let message = (error as? Failure)?.message ?? error.localizedDescription
        label.stringValue = message
        spinner.stopAnimation(nil); spinner.isHidden = true
        retry.isHidden = !retryable
        finder.isHidden = target == nil || recycled
        close.isHidden = false
        close.title = tr("Close", "关闭")
        try? report(partial ? "partial" : "error", code: "Uninstall could not finish", message: message)
    }

    @objc func retryAction() { performUninstall() }
    @objc func finderAction() {
        if let url = target { NSWorkspace.shared.activateFileViewerSelecting([url]) }
    }
    @objc func closeAction() { NSApp.terminate(nil) }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if busy && !canAbandonRecycle { return .terminateCancel }
        if busy {
            abandoned = true
            try? report("abandoned", message: tr("Stopped waiting. Settings and data were kept.", "已停止等待，设置和数据已保留。"))
        }
        return .terminateNow
    }
    func applicationWillTerminate(_ notification: Notification) {
        timer?.invalidate()
        try? fm.removeItem(at: folder) // Only this private helper session.
    }
}

do {
    guard CommandLine.arguments.count == 2 else { exit(2) }
    let folder = resolved(URL(fileURLWithPath: CommandLine.arguments[1]))
    // A copied helper can only consume the request beside its own bundle.
    guard Bundle.main.bundleIdentifier == "com.deskmate.companion.uninstaller",
          resolved(Bundle.main.bundleURL.deletingLastPathComponent()).path == folder.path,
          folder.lastPathComponent.hasPrefix("deskmate-uninstall-") else { exit(2) }
    let request = try JSONDecoder().decode(Request.self, from: Data(contentsOf: folder.appendingPathComponent("request.json")))
#if UNINSTALL_TESTING
    let testRoot = resolved(URL(fileURLWithPath: request.testDataRoot))
    guard testRoot.deletingLastPathComponent().path == "/private/tmp",
          testRoot.lastPathComponent.hasPrefix("deskmate-uninstall-test-"),
          request.bundle.isEmpty || request.bundle.hasPrefix(testRoot.path + "/") else { exit(2) }
#endif
    let app = NSApplication.shared
    app.setActivationPolicy(.accessory)
    let delegate = Uninstaller(folder: folder, request: request)
    app.delegate = delegate
    app.run()
    withExtendedLifetime(delegate) {}
} catch {
#if UNINSTALL_TESTING
    print("helper startup error:", error)
#endif
    exit(2)
}
