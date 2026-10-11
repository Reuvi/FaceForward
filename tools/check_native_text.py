#!/usr/bin/env python3
"""Opt-in macOS driver check: type only into this tool's temporary native fields."""
import argparse
import ctypes as ct
import os
from pathlib import Path
import platform
import sys
import time
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Drivers.binding import Config, Frame, load_driver
from Drivers.output import default_library


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Allow real keys in the temporary test window')
    args = parser.parse_args()
    if not args.live or platform.system() != 'Darwin':
        parser.error('This native check requires macOS and explicit --live')
    ct.CDLL('/System/Library/Frameworks/AppKit.framework/AppKit')
    objc = ct.CDLL('/usr/lib/libobjc.A.dylib')
    objc.objc_getClass.argtypes=[ct.c_char_p];objc.objc_getClass.restype=ct.c_void_p
    objc.sel_registerName.argtypes=[ct.c_char_p];objc.sel_registerName.restype=ct.c_void_p
    send = ct.CFUNCTYPE(ct.c_void_p,ct.c_void_p,ct.c_void_p)(('objc_msgSend',objc))
    send_bool = ct.CFUNCTYPE(None,ct.c_void_p,ct.c_void_p,ct.c_bool)(('objc_msgSend',objc))
    send_pid = ct.CFUNCTYPE(ct.c_int,ct.c_void_p,ct.c_void_p)(('objc_msgSend',objc))
    activate = ct.CFUNCTYPE(ct.c_bool,ct.c_void_p,ct.c_void_p,ct.c_ulong)(('objc_msgSend',objc))
    def call(obj, method):return send(obj,objc.sel_registerName(method.encode()))
    workspace=call(objc.objc_getClass(b'NSWorkspace'),'sharedWorkspace')
    def frontmost_pid():
        return send_pid(call(workspace,'frontmostApplication'),objc.sel_registerName(b'processIdentifier'))
    previous=call(workspace,'frontmostApplication')
    root=tk.Tk();root.title('Temporary Return and dictation driver test')
    tk.Label(root,text='Automatic local test — no web forms or messages are submitted.').pack(padx=20,pady=8)
    text=tk.Text(root,width=55,height=5);text.pack(padx=20,pady=8)
    entry=tk.Entry(root,width=55);entry.pack(padx=20,pady=8)
    submitted=[]
    entry.bind('<Return>',lambda event:submitted.append(entry.get()))
    root.update()
    app=call(objc.objc_getClass(b'NSApplication'),'sharedApplication')
    send_bool(app,objc.sel_registerName(b'activateIgnoringOtherApps:'),True)
    lib=load_driver(default_library());config=Config();lib.fid_default_config(ct.byref(config))
    config.backend=1;handle=ct.c_void_p();frame=Frame();lib.fid_neutral_frame(ct.byref(frame))
    def check(code):
        if code:raise RuntimeError(lib.fid_result_string(code).decode())
    def drain():
        end=time.monotonic()+.075
        while time.monotonic()<end:root.update();time.sleep(.003)
    def focus(widget):
        root.lift();widget.focus_force();drain()
        if frontmost_pid()!=os.getpid() or root.focus_get()!=widget:
            raise RuntimeError('Test window is not focused; no keys sent.')
    def guard(widget):
        if frontmost_pid()!=os.getpid() or root.focus_get()!=widget:
            raise RuntimeError('Focus changed; test cancelled before sending another key.')
        check(lib.fid_submit_processed(handle,ct.byref(frame)))
    def type_text(widget, value):
        for char in value:
            guard(widget);check(lib.fid_type_character(handle,ord(char)));drain()
    def press_return(widget):
        guard(widget);check(lib.fid_set_presentation(handle,1,0));drain()
        guard(widget);check(lib.fid_set_presentation(handle,0,0));drain()
    try:
        focus(text)
        check(lib.fid_create(ct.byref(config),ct.byref(handle)))
        check(lib.fid_enable(handle));check(lib.fid_submit_processed(handle,ct.byref(frame)))
        type_text(text,'Hello é🙂');press_return(text);type_text(text,'Second line')
        if text.get('1.0','end-1c')!='Hello é🙂\nSecond line':
            raise AssertionError('Driver text/Return mismatch: '+repr(text.get('1.0','end-1c')))
        print('PASS: native Unicode typing and Return inserted a newline.')
        focus(entry);type_text(entry,'Local field result');press_return(entry)
        if submitted!=['Local field result']:
            raise AssertionError('Return did not activate the single-line field exactly once')
        print('PASS: native Return activated a single-line field exactly once.')
    finally:
        if handle.value:lib.fid_pause(handle);lib.fid_destroy(handle)
        restore=frontmost_pid()==os.getpid()
        root.destroy()
        if restore:activate(previous,objc.sel_registerName(b'activateWithOptions:'),2)


if __name__=='__main__':main()
