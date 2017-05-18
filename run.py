# -*- coding: utf-8 -*-
import queue
import subprocess
import threading
import sys
import os
import datetime
from unittest.mock import MagicMock
from tkinter import *
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk
from pprint import pprint, pformat

from helper import parse_params, map_params, parse_ios_params, ios_chunk, map_adwords_params, parse_adwords_params
from helper import is_ios, is_android

root = Tk()
root.title("GA log formater")

mainframe = ttk.Frame(root, padding='3 3 3 3')
mainframe.grid(column=0, row=0, sticky=(N, W, E, S))
mainframe.columnconfigure(0, weight=1)
mainframe.rowconfigure(1, weight=1)

buttons_frame = ttk.Frame(mainframe)
buttons_frame.grid(column=0, row=0, sticky=(W, E))

filter_string = StringVar()
filter_entry = ttk.Entry(buttons_frame, textvariable=filter_string)
filter_entry.pack(side=LEFT)
#filter_entry.grid(row=0, columnspan=2, sticky=(W, N))


log_text = Text(mainframe)
log_text.grid(row=1, sticky=(N, W, E, S))
log_text_scrollbar = ttk.Scrollbar(mainframe, orient=VERTICAL, command=log_text.yview)
log_text_scrollbar.grid(column=1, row=1, sticky=(N,S))
log_text['yscrollcommand'] = log_text_scrollbar.set
log_text.tag_config('timestamp', foreground='red', justify='right')

root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)

filter_entry.focus()

track_ids = {}
interesting = set()


def cb(track_id):
    if track_ids[track_id].get():
        interesting.add(track_id)
        # log_text.tag_config(track_id, foreground='black')
    else:
        interesting.discard(track_id)
        # log_text.tag_config(track_id, foreground='darkgray')
        ranges = log_text.tag_ranges(track_id)
        for i in range(len(ranges), 0, -2):
            log_text.delete(ranges[i-2], ranges[i-1])


class AsynchronousFileReader(threading.Thread):
    '''
    Helper class to implement asynchronous reading of a file
    in a separate thread. Pushes read lines on a queue to
    be consumed in another thread.
    '''

    def __init__(self, fd, queue_):
        assert isinstance(queue_, queue.Queue)
        assert callable(fd.readline)
        threading.Thread.__init__(self)
        self._fd = fd
        self._queue = queue_

    def run(self):
        '''The body of the tread: read lines and put them on the queue.'''
        #for line in iter(self._fd.readline, None):
        #    if line == b'': break
            # self._queue.put(line.decode('utf-8').strip())
        while True:
            if is_ios():
                chunk = ios_chunk(iter(self._fd.readline, None))
                chunk = '\n'.join([str(line.replace(b'\U', b'\u'), encoding='unicode_escape') for line in chunk])
                parsed_dict = map_params(parse_ios_params(chunk))
                parsed_adwords_dict = {}
            elif is_android():
                line = next(iter(self._fd.readline, None))
                if line == b'':
                    break
                parsed_dict = map_params(parse_params(line.decode('utf-8').strip()))
                parsed_adwords_dict = map_adwords_params(parse_adwords_params(line.decode('utf-8').strip()))
            else:
                line = self._fd.readline()
                parsed_dict = {'Warning': line.strip()}
                parsed_adwords_dict = {}
            if parsed_dict == {} and parsed_adwords_dict == {}:
                continue
            track_id = parsed_dict.get('Tracking ID / Web Property ID') or parsed_adwords_dict.get('Conversion Id')
            if track_id:
                if track_id not in track_ids:
                    interesting.add(track_id)
                    var = IntVar(value=1)
                    track_ids[track_id] = var
                    b = Checkbutton(buttons_frame, text=track_id, variable=var, command=lambda track_id=track_id: cb(track_id))
                    b.pack(side=LEFT)
                if track_id not in interesting:
                    continue
            log_text.insert(END, "\n" + pformat(datetime.datetime.now()) + "\n", ('timestamp', track_id))
            if parsed_dict != {}:
                log_text.insert(END, pformat(parsed_dict) + "\n", track_id)
            if parsed_adwords_dict != {}:
                log_text.insert(END, pformat(parsed_adwords_dict) + "\n", track_id)
            log_text.see(END)

    def eof(self):
        '''Check whether there is no more content to expect.'''
        return not self.is_alive() and self._queue.empty()


# You'll need to add any command line arguments here.
if getattr(subprocess, 'STARTUPINFO', None):
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
else:
    startupinfo = None

if is_android():
    subprocess.Popen(['adb', 'shell', 'setprop', 'log.tag.GAv4', 'DEBUG'],
                     env=os.environ)
    process = subprocess.Popen(['adb', "logcat", "-s", "GAv4", "GoogleTagManager", "ArbitraryPixel"],
                               stdout=subprocess.PIPE,
                               startupinfo=startupinfo,
                               env=os.environ)
elif is_ios():
    process = subprocess.Popen(['sudo', 'idevicesyslog'], stdout=subprocess.PIPE, env=os.environ)
else:
    process = MagicMock()
    description = '''
    Not found iOS or Android device
    Check USB cable connection
    or check install of 'adb' or 'libimobiledevice'
    '''
    desc_iter = iter(description.split('\n'))
    process.stdout.readline = lambda :next(desc_iter)
# Launch the asynchronous readers of the process' stdout.
stdout_queue = queue.Queue()
stdout_reader = AsynchronousFileReader(process.stdout, stdout_queue)
stdout_reader.start()

root.mainloop()
process.kill()
