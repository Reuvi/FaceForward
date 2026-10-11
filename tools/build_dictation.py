#!/usr/bin/env python3
"""Build the local macOS speech helper; never requests permissions or records."""
import argparse
import hashlib
from pathlib import Path
import plistlib
import platform
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path.home()/'Library/Caches/FaceController'/hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]/'FaceControllerDictation.app')
    args = parser.parse_args()
    if platform.system() != 'Darwin':
        parser.error('The native dictation provider requires macOS')
    contents = args.output.resolve()/'Contents'
    binary = contents/'MacOS/FaceControllerDictation'
    binary.parent.mkdir(parents=True, exist_ok=True)
    plist = contents/'Info.plist'
    plist.write_bytes(plistlib.dumps(dict(CFBundleExecutable=binary.name,
        CFBundleIdentifier='org.facecontroller.dictation', CFBundleName='Face Controller Dictation',
        CFBundlePackageType='APPL', CFBundleVersion='1', CFBundleShortVersionString='1.0',
        LSUIElement=True, NSMicrophoneUsageDescription='Transcribe speech after you start dictation with both eyes.',
        NSSpeechRecognitionUsageDescription='Recognize speech on this Mac and type it only when you finish dictation.')))
    subprocess.run(['xcrun','swiftc','-swift-version','5','-O',str(ROOT/'App/speech/Dictation.swift'),
        '-module-cache-path',str(contents.parent.parent/'ModuleCache'),
        '-framework','Speech','-framework','AVFoundation',
        '-Xlinker','-sectcreate','-Xlinker','__TEXT','-Xlinker','__info_plist','-Xlinker',str(plist),
        '-o',str(binary)],check=True)
    subprocess.run(['xattr','-cr',str(args.output.resolve())],check=True)
    subprocess.run(['codesign','--force','--sign','-',str(args.output.resolve())],check=True)
    print(binary)


if __name__ == '__main__':
    main()
