// Local, non-activating speech helper. JSON lines on stdout; commands on stdin.
import Foundation
import AVFoundation
import Speech
import Darwin

func emit(_ state: String, _ message: String = "", text: String? = nil, code: String? = nil) {
    var value: [String: Any] = ["state": state, "message": message]
    if let code = code { value["code"] = code }
    if let text = text { value["text"] = String(text.prefix(10000)) }
    if let data = try? JSONSerialization.data(withJSONObject: value) {
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data([10]))
    }
}

final class Dictation {
    let recognizer = SFSpeechRecognizer(locale: Locale.current)
    let engine = AVAudioEngine()
    var request: SFSpeechAudioBufferRecognitionRequest?
    var task: SFSpeechRecognitionTask?
    var transcript = ""
    var finishing = false
    var ended = false
    var tapInstalled = false
    var finalReceived = false
    var sessionLimit: DispatchWorkItem?
    var fileMode = false

    func fail(_ message: String, code: String = "recognition_failed") {
        guard !ended else { return }
        ended = true
        cleanup()
        emit("error", message, code: code)
        exit(1)
    }

    func cleanup() {
        sessionLimit?.cancel()
        engine.stop()
        if tapInstalled { engine.inputNode.removeTap(onBus: 0); tapInstalled = false }
        request?.endAudio()
        task?.cancel()
    }

    func ready(microphone: Bool = true) -> Bool {
        guard SFSpeechRecognizer.authorizationStatus() == .authorized else {
            fail("Speech permission needed. Click Set up dictation; allow Face Controller Dictation in Privacy & Security > Speech Recognition.", code: "speech_permission")
            return false
        }
        guard !microphone || AVCaptureDevice.authorizationStatus(for: .audio) == .authorized else {
            fail("Microphone permission needed. Click Set up dictation; allow Face Controller Dictation in Privacy & Security > Microphone.", code: "microphone_permission")
            return false
        }
        guard let recognizer = recognizer, recognizer.isAvailable,
              recognizer.supportsOnDeviceRecognition else {
            fail("On-device speech is unavailable for this Mac/language. Enable and download your language in System Settings > Keyboard > Dictation, then retry setup. No cloud fallback is used.", code: "on_device_unavailable")
            return false
        }
        return true
    }

    func start(file: String? = nil) {
        fileMode = file != nil
        guard ready(microphone: !fileMode) else { return }
        let request: SFSpeechRecognitionRequest
        if let file = file {
            request = SFSpeechURLRecognitionRequest(url: URL(fileURLWithPath: file))
        } else {
            let audio = SFSpeechAudioBufferRecognitionRequest()
            self.request = audio
            request = audio
        }
        request.requiresOnDeviceRecognition = true
        request.shouldReportPartialResults = true
        request.taskHint = .dictation
        task = recognizer?.recognitionTask(with: request) { [weak self] result, error in
            DispatchQueue.main.async {
                guard let self = self, !self.ended else { return }
                if let result = result {
                    self.transcript = String(result.bestTranscription.formattedString.prefix(10000))
                    emit("partial", "Listening", text: self.transcript)
                    if result.isFinal {
                        self.finalReceived = true
                        self.stopAudio()
                        if self.finishing || self.fileMode { self.complete() }
                        else { emit("captured", "Speech captured — close both eyes to send", text: self.transcript) }
                        return
                    }
                }
                if let error = error {
                    self.fail("Speech recognition failed: \(error.localizedDescription). Nothing was sent; retry dictation.")
                }
            }
        }
        if fileMode {
            DispatchQueue.main.asyncAfter(deadline: .now()+30) { [weak self] in
                self?.fail("Audio-file check timed out.", code: "file_timeout")
            }
            return
        }
        guard let audio = self.request else { return }
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else {
            fail("No usable microphone. Select an input in System Settings > Sound.", code: "microphone_unavailable")
            return
        }
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            audio.append(buffer)
        }
        tapInstalled = true
        do {
            engine.prepare()
            try engine.start()
            emit("listening", "Listening — close both eyes to finish")
            let limit = DispatchWorkItem { [weak self] in
                guard let self = self, !self.ended else { return }
                self.stopAudio()
                emit("captured", "Recording limit reached — close both eyes to send", text: self.transcript)
            }
            sessionLimit = limit
            DispatchQueue.main.asyncAfter(deadline: .now()+55, execute: limit)
        } catch { fail("Microphone could not start: \(error.localizedDescription)", code: "microphone_start") }
    }

    func stopAudio() {
        sessionLimit?.cancel()
        engine.stop()
        if tapInstalled { engine.inputNode.removeTap(onBus: 0); tapInstalled = false }
        request?.endAudio()
    }

    func finish() {
        guard !ended, !finishing else { return }
        finishing = true
        emit("finalizing", "Finishing recognition")
        stopAudio()
        if finalReceived { complete(); return }
        // Never silently promote a partial hypothesis after a speech failure.
        DispatchQueue.main.asyncAfter(deadline: .now()+5) { [weak self] in
            guard let self = self, !self.ended else { return }
            self.fail("Speech did not finalize in time. Nothing was sent; retry dictation.", code: "finalize_timeout")
        }
    }

    func complete() {
        guard !ended else { return }
        ended = true
        cleanup()
        emit("final", "Ready to type", text: transcript)
        exit(0)
    }
}

// LaunchServices gives this signed bundle its own TCC permission identity. The
// parent creates a private socket before launch; EOF always ends microphone use.
func argument(_ flag: String) -> String? {
    guard let i = CommandLine.arguments.firstIndex(of: flag), i+1 < CommandLine.arguments.count else { return nil }
    return CommandLine.arguments[i+1]
}
if let path = argument("--socket") {
    var address = sockaddr_un()
    address.sun_family = sa_family_t(AF_UNIX)
    let bytes = Array(path.utf8CString)
    guard bytes.count <= MemoryLayout.size(ofValue: address.sun_path) else { exit(2) }
    withUnsafeMutableBytes(of: &address.sun_path) { raw in
        bytes.withUnsafeBytes { source in raw.copyMemory(from: source) }
    }
    address.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
    let fd = socket(AF_UNIX, SOCK_STREAM, 0)
    let result = withUnsafePointer(to: &address) {
        $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
        }
    }
    guard fd >= 0, result == 0 else { exit(2) }
    dup2(fd, STDIN_FILENO); dup2(fd, STDOUT_FILENO); close(fd)
}
if CommandLine.arguments.contains("--status") {
    emit("status", "Speech authorization \(SFSpeechRecognizer.authorizationStatus().rawValue); microphone authorization \(AVCaptureDevice.authorizationStatus(for: .audio).rawValue)")
    exit(0)
}
let service = Dictation()
func checkPermissions() {
    SFSpeechRecognizer.requestAuthorization { _ in
        AVCaptureDevice.requestAccess(for: .audio) { _ in
            DispatchQueue.main.async {
                if service.ready() { emit("ready", "On-device dictation ready. Focus a text field, start live control, then hold both eyes until the listening sound."); exit(0) }
            }
        }
    }
}
if CommandLine.arguments.contains("--check") {
    checkPermissions()
} else if let file = argument("--transcribe-file") {
    // Explicit developer verification of on-device recognition, without a mic.
    DispatchQueue.main.async { service.start(file: file) }
} else if argument("--socket") != nil {
    var started = false
    DispatchQueue.main.asyncAfter(deadline: .now()+10) {
        if !started { service.cleanup(); exit(0) }
    }
    DispatchQueue.global(qos: .userInitiated).async {
        while let line = readLine() {
            DispatchQueue.main.async {
                if line == "start" && !started { started = true; service.start() }
                else if line == "check" && !started { started = true; checkPermissions() }
                else if line == "finish" && started { service.finish() }
                else if line == "cancel" { service.cleanup(); exit(0) }
            }
        }
        DispatchQueue.main.async { service.cleanup(); exit(0) }
    }
} else {
    emit("error", "Start dictation from App so macOS uses the speech bundle's permissions.", code: "launch_required")
    exit(1)
}
RunLoop.main.run()
