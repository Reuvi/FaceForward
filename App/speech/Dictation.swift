// Local, non-activating speech helper. JSON lines on stdout; commands on stdin.
import Foundation
import AVFoundation
import Speech

func emit(_ state: String, _ message: String = "", text: String? = nil) {
    var value: [String: Any] = ["state": state, "message": message]
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

    func fail(_ message: String) {
        guard !ended else { return }
        ended = true
        cleanup()
        emit("error", message)
        exit(1)
    }

    func cleanup() {
        sessionLimit?.cancel()
        engine.stop()
        if tapInstalled { engine.inputNode.removeTap(onBus: 0); tapInstalled = false }
        request?.endAudio()
        task?.cancel()
    }

    func ready() -> Bool {
        guard SFSpeechRecognizer.authorizationStatus() == .authorized else {
            fail("Speech permission needed. Click Set up dictation; allow Speech Recognition in Privacy & Security.")
            return false
        }
        guard AVCaptureDevice.authorizationStatus(for: .audio) == .authorized else {
            fail("Microphone permission needed. Click Set up dictation; allow Microphone in Privacy & Security.")
            return false
        }
        guard let recognizer = recognizer, recognizer.isAvailable,
              recognizer.supportsOnDeviceRecognition else {
            fail("On-device speech is unavailable for this Mac/language. Enable and download your language in System Settings > Keyboard > Dictation, then retry setup. No cloud fallback is used.")
            return false
        }
        return true
    }

    func start() {
        guard ready() else { return }
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.requiresOnDeviceRecognition = true
        request.shouldReportPartialResults = true
        request.taskHint = .dictation
        self.request = request
        task = recognizer?.recognitionTask(with: request) { [weak self] result, error in
            DispatchQueue.main.async {
                guard let self = self, !self.ended else { return }
                if let result = result {
                    self.transcript = String(result.bestTranscription.formattedString.prefix(10000))
                    emit("partial", "Listening", text: self.transcript)
                    if result.isFinal {
                        self.finalReceived = true
                        self.stopAudio()
                        if self.finishing { self.complete() }
                        else { emit("captured", "Speech captured — close both eyes to send", text: self.transcript) }
                        return
                    }
                }
                if let error = error {
                    self.fail("Speech recognition failed: \(error.localizedDescription). Nothing was sent; retry dictation.")
                }
            }
        }
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else {
            fail("No usable microphone. Select an input in System Settings > Sound.")
            return
        }
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            request.append(buffer)
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
        } catch { fail("Microphone could not start: \(error.localizedDescription)") }
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
            self.fail("Speech did not finalize in time. Nothing was sent; retry dictation.")
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

let check = CommandLine.arguments.contains("--check")
if CommandLine.arguments.contains("--status") {
    emit("status", "Speech authorization \(SFSpeechRecognizer.authorizationStatus().rawValue); microphone authorization \(AVCaptureDevice.authorizationStatus(for: .audio).rawValue)")
    exit(0)
}
let service = Dictation()
if check {
    SFSpeechRecognizer.requestAuthorization { _ in
        AVCaptureDevice.requestAccess(for: .audio) { _ in
            DispatchQueue.main.async {
                if service.ready() { emit("ready", "On-device dictation ready"); exit(0) }
            }
        }
    }
} else {
    DispatchQueue.main.async { service.start() }
    DispatchQueue.global(qos: .userInitiated).async {
        while let line = readLine() {
            DispatchQueue.main.async {
                if line == "finish" { service.finish() }
                else if line == "cancel" { service.cleanup(); exit(0) }
            }
        }
        DispatchQueue.main.async { service.cleanup(); exit(0) }
    }
}
RunLoop.main.run()
