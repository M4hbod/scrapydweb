# coding: utf-8
import argparse
import logging
import os
import sys

import uvicorn

# python -m scrapydweb.run
from scrapydweb import create_app
from scrapydweb.__version__ import __description__, __version__
from scrapydweb.common import handle_metadata
from scrapydweb.vars import SCHEDULER_STATE_DICT, STATE_PAUSED, STATE_RUNNING
from scrapydweb.utils.check_app_config import check_app_config


logger = logging.getLogger(__name__)
apscheduler_logger = logging.getLogger('apscheduler')

STAR = '\n%s\n' % ('*' * 100)


def main():
    apscheduler_logger.setLevel(logging.ERROR)  # To hide warning logging in scheduler.py until app.run()
    main_pid = os.getpid()
    logger.info("ScrapydWeb version: %s", __version__)
    logger.info("Use 'scrapydweb -h' to get help")
    logger.info("Main pid: %s", main_pid)
    app = create_app()
    handle_metadata('main_pid', main_pid)
    app.config['MAIN_PID'] = main_pid

    args = parse_args(app.config)
    # "scrapydweb -h" ends up here
    update_app_config(app.config, args)
    try:
        check_app_config(app.config)
    except AssertionError as err:
        logger.error("Check app config fail: ")
        sys.exit(u"\n{err}\n\nFix the setting in the web UI (Settings page) "
                 u"or via environment variables, then restart.\n".format(err=err))

    # Basic auth is handled by an ASGI middleware in create_app() (reads settings per request).
    if app.config.get('ENABLE_HTTPS', False):
        protocol = 'https'
        ssl_kwargs = dict(ssl_certfile=app.config['CERTIFICATE_FILEPATH'],
                          ssl_keyfile=app.config['PRIVATEKEY_FILEPATH'])
    else:
        protocol = 'http'
        ssl_kwargs = {}

    print("{star}Visit ScrapydWeb at {protocol}://127.0.0.1:{port} "
          "or {protocol}://IP-OF-THE-CURRENT-HOST:{port}{star}\n".format(
           star=STAR, protocol=protocol, port=app.config['SCRAPYDWEB_PORT']))
    apscheduler_logger.setLevel(logging.DEBUG)
    uvicorn.run(app, host=app.config['SCRAPYDWEB_BIND'], port=int(app.config['SCRAPYDWEB_PORT']),
                **ssl_kwargs)


def parse_args(config):
    parser = argparse.ArgumentParser(description='ScrapydWeb -- %s' % __description__)

    SCRAPYDWEB_BIND = config.get('SCRAPYDWEB_BIND', '0.0.0.0')
    parser.add_argument(
        '-b', '--bind',
        default=SCRAPYDWEB_BIND,
        help=("current: %s, note that setting to 0.0.0.0 or IP-OF-THE-CURRENT-HOST would make ScrapydWeb server "
              "visible externally, otherwise, type '-b 127.0.0.1'") % SCRAPYDWEB_BIND
    )

    SCRAPYDWEB_PORT = config.get('SCRAPYDWEB_PORT', 5000)
    parser.add_argument(
        '-p', '--port',
        default=SCRAPYDWEB_PORT,
        help="current: %s, accept connections on the specified port" % SCRAPYDWEB_PORT
    )

    SCRAPYD_SERVERS = config.get('SCRAPYD_SERVERS', []) or ['(none configured)']
    parser.add_argument(
        '-ss', '--scrapyd_server',
        action='append',
        help=("current: %s, type '-ss 127.0.0.1 -ss username:password@192.168.123.123:6801#group' "
              "to set up more than one Scrapyd server to manage. ") % SCRAPYD_SERVERS
    )


    CHECK_SCRAPYD_SERVERS = config.get('CHECK_SCRAPYD_SERVERS', True)
    parser.add_argument(
        '-dc', '--disable_check_scrapyd',
        action='store_true',
        help="current: CHECK_SCRAPYD_SERVERS = %s, append '--disable_check_scrapyd' skip checking connectivity of scrapyd" % CHECK_SCRAPYD_SERVERS
    )

    SCHEDULER_STATE = SCHEDULER_STATE_DICT[handle_metadata().get('scheduler_state', STATE_RUNNING)]
    parser.add_argument(
        '-sw', '--switch_scheduler_state',
        action='store_true',
        help=("current: %s, append '--switch_scheduler_state' to switch the state of scheduler "
              "for timer tasks") % SCHEDULER_STATE
    )


    DEBUG = config.get('DEBUG', False)
    parser.add_argument(
        '-d', '--debug',
        action='store_true',
        help=("current: DEBUG = %s, append '--debug' to enable debug mode "
              "and the debugger would be available in the browser") % DEBUG
    )

    VERBOSE = config.get('VERBOSE', False)
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help=("current: VERBOSE = %s, append '--verbose' to set the logging level to DEBUG "
              "for getting more information about how ScrapydWeb works") % VERBOSE
    )

    return parser.parse_args()


def update_app_config(config, args):
    logger.debug("Reading settings from command line: %s", args)

    config.update(dict(
        SCRAPYDWEB_BIND=args.bind,
        SCRAPYDWEB_PORT=args.port,
    ))

    # scrapyd_server would be None if the -ss argument is not passed in
    if args.scrapyd_server:
        config['SCRAPYD_SERVERS'] = args.scrapyd_server

    # action='store_true': default False
    if args.disable_check_scrapyd:
        config['CHECK_SCRAPYD_SERVERS'] = False
    if args.switch_scheduler_state:
        if handle_metadata().get('scheduler_state', STATE_RUNNING) == STATE_RUNNING:
            handle_metadata('scheduler_state', STATE_PAUSED)
        else:
            handle_metadata('scheduler_state', STATE_RUNNING)
    if args.debug:
        config['DEBUG'] = True
    if args.verbose:
        config['VERBOSE'] = True


if __name__ == '__main__':
    main()
