#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# filename: cli.py
# modified: 2020-02-20

from optparse import OptionParser
from threading import Thread
import time
from multiprocessing import Queue
from . import __version__, __date__


def create_default_parser():

    parser = OptionParser(
        description='PKU Auto-Elective Tool v%s (%s)' % (__version__, __date__),
        version=__version__,
    )

    ## custom input files

    parser.add_option(
        '-c',
        '--config',
        dest='config_ini',
        metavar="FILE",
        help='custom config file encoded with utf8',
    )

    ## boolean (flag) options

    parser.add_option(
        '-m',
        '--with-monitor',
        dest='with_monitor',
        action='store_true',
        default=False,
        help='run the monitor thread simultaneously',
    )

    return parser


def setup_default_environ(options, args, environ):

    environ.config_ini = options.config_ini
    environ.with_monitor = options.with_monitor


def create_default_threads(options, args, environ):

    # import here to ensure the singleton `config` will be init later than parse_args()
    from autoelective.loop import run_iaaa_loop, run_elective_loop
    from autoelective.monitor import run_monitor

    tList = []

    t = Thread(target=run_iaaa_loop, name="IAAA")
    environ.iaaa_loop_thread = t
    tList.append(t)

    t = Thread(target=run_elective_loop, name="Elective")
    environ.elective_loop_thread = t
    tList.append(t)

    if options.with_monitor:
        t = Thread(target=run_monitor, name="Monitor")
        environ.monitor_thread = t
        tList.append(t)

    return tList


def run():

    from .environ import Environ
    from .logger import ConsoleLogger

    environ = Environ()
    cout = ConsoleLogger("cli")

    parser = create_default_parser()
    options, args = parser.parse_args()

    setup_default_environ(options, args, environ)

    # Import modules that instantiate AutoElectiveConfig only after config path is set.
    # Otherwise `main.py -c xxx.ini` would be ignored due to early singleton init.
    from autoelective.loop import run_iaaa_loop, run_elective_loop
    from autoelective.monitor import run_monitor

    def _start_thread(t):
        t.daemon = True
        t.start()
        return t

    # initial threads
    environ.iaaa_loop_thread = _start_thread(Thread(target=run_iaaa_loop, name="IAAA"))
    environ.elective_loop_thread = _start_thread(Thread(target=run_elective_loop, name="Elective"))
    if options.with_monitor:
        environ.monitor_thread = _start_thread(Thread(target=run_monitor, name="Monitor"))

    thread_specs = [
        ("IAAA", "iaaa_loop_thread", run_iaaa_loop),
        ("Elective", "elective_loop_thread", run_elective_loop),
    ]
    if options.with_monitor:
        thread_specs.append(("Monitor", "monitor_thread", run_monitor))

    last_restart = {}
    try:
        while True:
            time.sleep(1.0)
            for name, attr, target in thread_specs:
                t = getattr(environ, attr)
                if t is not None and t.is_alive():
                    continue
                now = time.time()
                last = last_restart.get(name, 0)
                if now - last < 5.0:
                    continue
                cout.warning("Thread %s not alive, restarting" % name)
                nt = _start_thread(Thread(target=target, name=name))
                setattr(environ, attr, nt)
                last_restart[name] = now
    except KeyboardInterrupt as e:
        pass
