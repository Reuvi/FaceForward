"""Bounded local speech provider and cancellable presentation text orchestration."""
from collections import deque
from pathlib import Path
import platform
import queue
import threading

from .paths import DICTATION_BUNDLE
from .speech_transport import SpeechProcess
from .dictation_sounds import DictationSounds

HELPER = DICTATION_BUNDLE/'Contents/MacOS/FaceControllerDictation'
ERROR_CODES = frozenset(('dictation_failure', 'provider_failure', 'helper_exit', 'speech_failure',
    'speech_permission', 'microphone_permission', 'on_device_unavailable', 'recognition_failed',
    'microphone_unavailable', 'microphone_start', 'finalize_timeout', 'file_timeout', 'launch_required'))


class MacSpeechProvider:
    """Starts helpers off the control clock. No audio/transcript files or network."""
    def __init__(self, helper=HELPER):
        self.helper = Path(helper)
        self.events = queue.Queue(maxsize=128)
        self.lock = threading.Lock()
        self.generation = 0
        self.process = None
        self.finish_requested = False

    def post(self, generation, item):
        with self.lock:
            if generation != self.generation:
                return
            try:
                self.events.put_nowait(item)
            except queue.Full:
                self.events.get_nowait()
                self.events.put_nowait(item)

    def start(self, *, check=False):
        self.cancel()
        with self.lock:
            generation = self.generation
            self.finish_requested = False
        def run():
            process = None
            terminal = False
            try:
                if platform.system() != 'Darwin':
                    raise ValueError('Dictation currently requires macOS; head, click and Return remain available.')
                if not self.helper.is_file():
                    raise ValueError('Build dictation first: python3 tools/build_dictation.py, then click Set up dictation.')
                process = SpeechProcess(self.helper)
                with self.lock:
                    if generation != self.generation:
                        process.cancel()
                    else:
                        self.process = process
                for item in process.events('check' if check else 'start'):
                    if not isinstance(item, dict) or item.get('state') not in (
                            'partial','listening','captured','finalizing','final','ready','error'):
                        raise ValueError('Invalid speech provider response')
                    if not isinstance(item.get('text',''), str) or len(item.get('text','')) > 10000:
                        raise ValueError('Speech text exceeded its limit')
                    if not isinstance(item.get('message',''), str) or len(item.get('message','')) > 2000:
                        raise ValueError('Invalid speech provider message')
                    terminal |= item['state'] in ('final','ready','error')
                    self.post(generation, item)
                    if item['state'] == 'listening':
                        with self.lock:
                            if self.finish_requested:process.send('finish')
                if not terminal:
                    self.post(generation, dict(state='error', message='Speech app stopped before completion. Rebuild the helper and use Set up dictation; nothing was sent.', code='helper_exit'))
            except Exception as exc:
                self.post(generation, dict(state='error', message=str(exc), code='provider_failure'))
            finally:
                if process is not None:process.cancel()
                with self.lock:
                    if generation == self.generation:self.process = None
        threading.Thread(target=run, name='local-dictation-provider', daemon=True).start()

    def finish(self):
        with self.lock:
            self.finish_requested = True
            if self.process:self.process.send('finish')

    def poll(self):
        result = []
        for _ in range(128):
            try:result.append(self.events.get_nowait())
            except queue.Empty:break
        return result

    def cancel(self):
        with self.lock:
            self.generation += 1
            self.finish_requested = False
            if self.process is not None:self.process.cancel()
            self.process = None
            while True:
                try:self.events.get_nowait()
                except queue.Empty:break


class DictationController:
    """Called under Lab's lock; nonblocking start/poll and one character per tick."""
    BUSY = ('starting','listening','captured','finalizing','sending','submitting')

    def __init__(self, provider=None, *, allow_capture=None, cue=None):
        self.provider = provider or MacSpeechProvider()
        self.cue = cue if cue is not None else (DictationSounds() if provider is None else lambda active: None)
        self.listening = False
        self.error_code = None
        self.allow_capture = allow_capture or (lambda: provider is not None)
        self.state = 'idle'
        self.message = 'Set up dictation once, then hold both eyes closed to speak.'
        self.text = ''
        self.pending = deque()
        self.identity = None
        self.toggle = 0
        self.request_active = False
        self.started_at = self.finish_at = self.next_character = 0
        self.sent = 0
        self.setup_requested = False

    def set_listening(self, listening):
        if listening != self.listening:
            self.listening = listening
            try:self.cue(listening)
            except Exception:pass  # Audio feedback must never stop output cleanup.

    def setup(self):
        self.cancel('Checking microphone and speech permissions…')
        self.state = 'setup'
        self.setup_requested = True
        self.provider.start(check=True)

    def cancel(self, message='Dictation cancelled; unsent text discarded.'):
        self.provider.cancel()
        self.set_listening(False)
        self.error_code = None
        self.pending.clear()
        self.text = ''
        self.request_active = False
        self.state = 'idle'
        self.message = message
        self.setup_requested = False

    def fail(self, message, processor, code="dictation_failure"):
        self.cancel(message)
        self.state = 'error'
        self.error_code = code if isinstance(code, str) and code in ERROR_CODES else 'speech_failure'
        if hasattr(processor, 'cancel_dictation'):
            processor.cancel_dictation()

    def prepare(self, snap, output, now, processor):
        try:
            self._prepare(snap, output, now, processor)
        except Exception as exc:
            self.fail('Dictation stopped: '+str(exc), processor)
        snap['dictation'] = dict(state=self.state, message=self.message, text=self.text,
                                 remaining=len(self.pending), sent=self.sent, listening=self.listening, error_code=self.error_code)
        if self.state in ('finalizing','sending','submitting') and hasattr(processor, 'gestures'):
            processor.gestures.reset()  # Discard actions attempted while the text queue owns output.
        if self.state in self.BUSY or self.request_active:
            snap['pointer_x'] = snap['pointer_y'] = snap['scroll_y'] = .5
            snap['left_click'] = snap['right_click'] = 0
            if 'keys' in snap:snap['keys'] = dict.fromkeys(snap['keys'], 0)
            if 'presentation' in snap:
                snap['presentation'].update(enter=False, drag_left=False)
            processor.pointer.reset_motion()

    def _prepare(self, snap, output, now, processor):
        request = snap.get('dictation_request')
        identity = (snap.get('output_session_id'), id(output))
        live = bool(request is not None and snap['enabled'])
        if not live or identity != self.identity:
            if self.state in self.BUSY:
                self.cancel()
            self.request_active = False
            self.identity = identity
            self.toggle = request['toggle'] if request else 0
        if live and request['toggle'] != self.toggle:
            self.toggle = request['toggle']
            if request['active']:
                if self.state in self.BUSY:
                    self.fail('Previous dictation is still finishing. Reopen both eyes and retry.', processor)
                elif not self.allow_capture():
                    self.fail('Speech capture requires the Camera source. Synthetic/replay inputs cannot start the microphone.', processor)
                elif output is None or not output.snapshot().get('text_supported'):
                    self.fail('Connect the rebuilt Driver dry run or Live mouse + keyboard output before dictation.', processor)
                else:
                    self.error_code = None
                    self.provider.start()
                    self.state, self.message = 'starting', 'Starting on-device dictation…'
                    self.text = ''; self.pending.clear(); self.sent = 0
                    self.request_active = True
                    self.started_at = now
            elif self.request_active and self.state in ('starting','listening','captured'):
                self.provider.finish()
                self.set_listening(False)
                self.state, self.message = 'finalizing', 'Finishing recognition…'
                self.finish_at = now
                self.request_active = False
        for event in self.provider.poll():
            state = event['state']
            if state == 'error':
                self.fail(event.get('message', 'Speech failed; nothing was sent.'), processor,
                          event.get('code', 'speech_failure'))
                break
            if self.state == 'setup':
                if state == 'ready':
                    self.state, self.message = 'idle', event['message']
                    self.setup_requested = False
                continue
            if self.state not in self.BUSY:
                continue
            if state in ('listening','partial','captured'):
                if self.state != 'finalizing':
                    if state in ('listening', 'captured'):self.set_listening(state == 'listening')
                    self.state = 'captured' if state == 'captured' or self.state == 'captured' else 'listening'
                    self.message = event.get('message', 'Listening — close both eyes to finish')
                if 'text' in event:self.text = event['text']
            elif state == 'final' and self.state == 'finalizing':
                # The deliberate finish gesture submits after all text. Embedded
                # newlines/tabs become spaces so they cannot submit prematurely;
                # other controls, surrogates and invisible nonprinting text drop.
                text = ''.join(' ' if c in '\r\n\t' else c for c in event.get('text',''))
                text = ''.join(c for c in text if c.isprintable() and not 0xd800 <= ord(c) <= 0xdfff)
                self.text = text[:10000].strip()
                self.pending = deque(self.text)
                self.state = 'sending' if self.pending else 'idle'
                self.message = 'Typing into the focused field…' if self.pending else 'No speech detected; nothing sent.'
                self.next_character = now
        if self.state == 'starting' and now-self.started_at > 15000:
            self.fail('Speech did not start. Use Set up dictation and retry.', processor)
        if self.state == 'finalizing' and now-self.finish_at > 6500:
            self.fail('Speech did not finalize; nothing was sent.', processor)
        if self.state in ('listening','captured') and now-self.started_at > 120000:
            self.fail('Dictation cancelled after two minutes without a finish gesture.', processor)

    def after_submit(self, output, snap, now):
        if self.state not in ('sending','submitting') or not snap['enabled'] or now < self.next_character:
            return
        if self.state == 'submitting':
            output.press_return()
            self.state, self.message = 'idle', 'Text entered and Return sent.'
            self.text = ''
            return
        output.type_character(self.pending[0])
        self.pending.popleft()
        self.sent += 1
        self.next_character = now+35
        if not self.pending:
            # Wait for the next fresh output tick, keeping cancellation and the
            # watchdog effective between the last character and submission.
            self.state, self.message = 'submitting', 'Text entered — sending Return…'
