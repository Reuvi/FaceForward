"""Bounded local speech provider and cancellable presentation text orchestration."""
from collections import deque
import json
from pathlib import Path
import platform
import queue
import subprocess
import threading

from .paths import DICTATION_BUNDLE

HELPER = DICTATION_BUNDLE/'Contents/MacOS/FaceControllerDictation'


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
                    raise ValueError('Dictation currently requires macOS; head, click and Enter remain available.')
                if not self.helper.is_file():
                    raise ValueError('Build dictation first: python3 tools/build_dictation.py, then click Set up dictation.')
                process = subprocess.Popen([str(self.helper)]+(['--check'] if check else []),
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, encoding='utf-8', bufsize=1)
                with self.lock:
                    if generation != self.generation:
                        process.terminate()
                    else:
                        self.process = process
                        if self.finish_requested:
                            process.stdin.write('finish\n'); process.stdin.flush()
                for line in process.stdout:
                    if len(line) > 65536:
                        raise ValueError('Speech provider exceeded its message limit')
                    item = json.loads(line)
                    if not isinstance(item, dict) or item.get('state') not in (
                            'partial','listening','captured','finalizing','final','ready','error'):
                        raise ValueError('Invalid speech provider response')
                    if not isinstance(item.get('text',''), str) or len(item.get('text','')) > 10000:
                        raise ValueError('Speech text exceeded its limit')
                    terminal |= item['state'] in ('final','ready','error')
                    self.post(generation, item)
                process.wait(timeout=2)
                if not terminal:
                    self.post(generation, dict(state='error', message='Speech helper stopped before completion. Nothing was sent.'))
            except Exception as exc:
                self.post(generation, dict(state='error', message=str(exc)))
            finally:
                if process is not None:
                    if process.poll() is None:
                        process.terminate()
                        try:process.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            process.kill(); process.wait(timeout=1)
                    for stream in (process.stdin, process.stdout):
                        if stream:stream.close()
                with self.lock:
                    if generation == self.generation:self.process = None
        threading.Thread(target=run, name='local-dictation-provider', daemon=True).start()

    def finish(self):
        with self.lock:
            self.finish_requested = True
            if self.process and self.process.poll() is None:
                self.process.stdin.write('finish\n')
                self.process.stdin.flush()

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
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
            self.process = None
            while True:
                try:self.events.get_nowait()
                except queue.Empty:break


class DictationController:
    """Called under Lab's lock; nonblocking start/poll and one character per tick."""
    BUSY = ('starting','listening','captured','finalizing','sending')

    def __init__(self, provider=None, *, allow_capture=None):
        self.provider = provider or MacSpeechProvider()
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

    def setup(self):
        self.cancel('Checking microphone and speech permissions…')
        self.state = 'setup'
        self.setup_requested = True
        self.provider.start(check=True)

    def cancel(self, message='Dictation cancelled; unsent text discarded.'):
        self.provider.cancel()
        self.pending.clear()
        self.text = ''
        self.request_active = False
        self.state = 'idle'
        self.message = message
        self.setup_requested = False

    def fail(self, message, processor):
        self.cancel(message)
        self.state = 'error'
        if hasattr(processor, 'cancel_dictation'):
            processor.cancel_dictation()

    def prepare(self, snap, output, now, processor):
        try:
            self._prepare(snap, output, now, processor)
        except Exception as exc:
            self.fail('Dictation stopped: '+str(exc), processor)
        snap['dictation'] = dict(state=self.state, message=self.message, text=self.text,
                                 remaining=len(self.pending), sent=self.sent)
        if self.state in ('finalizing','sending') and hasattr(processor, 'gestures'):
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
                    self.provider.start()
                    self.state, self.message = 'starting', 'Starting on-device dictation…'
                    self.text = ''; self.pending.clear(); self.sent = 0
                    self.request_active = True
                    self.started_at = now
            elif self.request_active and self.state in ('starting','listening','captured'):
                self.provider.finish()
                self.state, self.message = 'finalizing', 'Finishing recognition…'
                self.finish_at = now
                self.request_active = False
        for event in self.provider.poll():
            state = event['state']
            if state == 'error':
                self.fail(event.get('message', 'Speech failed; nothing was sent.'), processor)
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
                    self.state = 'captured' if state == 'captured' else 'listening'
                    self.message = event.get('message', 'Listening — close both eyes to finish')
                if 'text' in event:self.text = event['text']
            elif state == 'final' and self.state == 'finalizing':
                # Dictation never auto-submits forms. Newlines/tabs become spaces;
                # other controls, surrogates and invisible nonprinting text drop.
                text = ''.join(' ' if c in '\r\n\t' else c for c in event.get('text',''))
                text = ''.join(c for c in text if c.isprintable() and not 0xd800 <= ord(c) <= 0xdfff)
                self.text = text[:10000]
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
        if self.state != 'sending' or not snap['enabled'] or now < self.next_character:
            return
        output.type_character(self.pending[0])
        self.pending.popleft()
        self.sent += 1
        self.next_character = now+35
        if not self.pending:
            self.state, self.message = 'idle', 'Text entered. Close and reopen your right eye to press Enter.'
            self.text = ''
