"""Local socket lifecycle with a fake app; no permissions, microphone or keys."""
import json
from pathlib import Path
import socket
import threading
import time
import unittest
from unittest.mock import patch

from App.speech_transport import SpeechProcess


class FakeApp:
    def __init__(self, args, *, reply=None, **kwargs):
        self.args=args
        self.done=threading.Event()
        self.connected=threading.Event()
        self.commands=[]
        self.reply=reply if reply is not None else dict(state='listening')
        def run():
            try:
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
                    connection.connect(args[-1]);self.connected.set()
                    with connection.makefile('r') as stream:
                        for line in stream:
                            self.commands.append(line.strip())
                            connection.sendall((json.dumps(self.reply)+'\n').encode())
            finally:self.done.set()
        self.thread=threading.Thread(target=run,daemon=True);self.thread.start()

    def poll(self):return 0 if self.done.is_set() else None
    def wait(self, timeout):
        if not self.done.wait(timeout):raise AssertionError('Socket EOF did not stop the fake app')
        return 0


class SpeechTransportTests(unittest.TestCase):
    def test_bundle_launch_preserves_focus_and_disconnect_ends_helper(self):
        app=[]
        def launch(*args,**kwargs):
            app.append(FakeApp(*args,**kwargs));return app[-1]
        helper=SpeechProcess('/tmp/Test.app/Contents/MacOS/FaceControllerDictation')
        with patch('App.speech_transport.subprocess.Popen',side_effect=launch):
            events=helper.events('start')
            self.assertEqual(next(events),dict(state='listening'))
            self.assertEqual(app[0].args[:5],['/usr/bin/open','-n','-g','-W','/tmp/Test.app'])
            self.assertEqual(app[0].commands,['start'])
            path=Path(app[0].args[-1]);self.assertEqual(path.parent.stat().st_mode & 0o777,0o700)
            helper.send('finish');self.assertEqual(next(events),dict(state='listening'))
            self.assertEqual(app[0].commands,['start','finish'])
            helper.cancel();self.assertEqual(list(events),[])
            self.assertTrue(app[0].done.is_set());self.assertFalse(path.exists())

    def test_cancel_interrupts_a_blocked_reader(self):
        app=[];helper=SpeechProcess('/tmp/Test.app/Contents/MacOS/FaceControllerDictation')
        def launch(*args,**kwargs):app.append(FakeApp(*args,**kwargs));return app[-1]
        with patch('App.speech_transport.subprocess.Popen',side_effect=launch):
            events=helper.events('start');next(events)
            stopped=threading.Event()
            def read():
                list(events);stopped.set()
            worker=threading.Thread(target=read,daemon=True);worker.start()
            helper.cancel()
            self.assertTrue(stopped.wait(2));worker.join(2)
            self.assertTrue(app[0].done.is_set())

    def test_cancel_before_start_cannot_launch_or_record(self):
        helper=SpeechProcess('/tmp/Test.app/Contents/MacOS/FaceControllerDictation')
        helper.cancel()
        with patch('App.speech_transport.subprocess.Popen') as launch:
            self.assertEqual(list(helper.events('start')),[])
            launch.assert_not_called()

    def test_provider_drops_late_results_and_handles_finish_before_listening(self):
        from App.dictation import MacSpeechProvider
        ready=threading.Event();proceed=threading.Event();sent=[]
        class DelayedProcess:
            def __init__(self, helper):pass
            def cancel(self):pass
            def send(self, command):sent.append(command)
            def events(self, command):
                ready.set();proceed.wait(2)
                yield dict(state='listening')
                yield dict(state='final',text='late private text')
        provider=MacSpeechProvider(__file__)
        with patch('App.dictation.SpeechProcess',DelayedProcess),patch('App.dictation.platform.system',return_value='Darwin'):
            provider.start();self.assertTrue(ready.wait(2));provider.finish();proceed.set()
            deadline=time.monotonic()+2
            while provider.process is not None and time.monotonic()<deadline:time.sleep(.005)
            self.assertIn('finish',sent)
            self.assertEqual([e['state'] for e in provider.poll()],['listening','final'])
            ready.clear();proceed.clear()
            provider.start();self.assertTrue(ready.wait(2));provider.cancel();proceed.set()
            time.sleep(.02)
            self.assertEqual(provider.poll(),[])


if __name__=='__main__':unittest.main()
