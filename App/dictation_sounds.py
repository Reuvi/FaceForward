"""Short rising/falling listening cues, played off the control clock."""
import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import threading
import wave


class DictationSounds:
    def __init__(self):
        self.player = shutil.which('afplay')
        self.lock = threading.Lock()
        self.generation = 0

    def __call__(self, listening):
        if not self.player:return
        with self.lock:
            self.generation += 1
            generation = self.generation
        def play():
            with self.lock:
                if generation != self.generation:return
            try:
                with tempfile.TemporaryDirectory(prefix='face-cue-') as folder:
                    path = Path(folder)/'cue.wav'
                    samples = []
                    rate, length = 22050, 2205
                    for frequency in ((660, 880) if listening else (660, 440)):
                        for i in range(length):
                            envelope = min(1, i/220, (length-1-i)/220)
                            samples.append(int(8000*envelope*math.sin(2*math.pi*frequency*i/rate)))
                    with wave.open(str(path), 'wb') as out:
                        out.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
                        out.writeframes(struct.pack('<'+'h'*len(samples), *samples))
                    subprocess.run([self.player, str(path)], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=2)
            except (OSError, subprocess.SubprocessError):pass
        threading.Thread(target=play, name='dictation-cue', daemon=True).start()
