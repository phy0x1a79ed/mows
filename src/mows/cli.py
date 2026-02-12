import os, sys
import argparse

from .utils import NAME, VERSION, ENTRY_POINTS

CLI_ENTRY = ENTRY_POINTS[0]

def _line():
    try:
        width = os.get_terminal_size().columns
    except:
        width = 32
    return "="*width

class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_help(sys.stderr)
        self.exit(2, '\n%s: error: %s\n' % (self.prog, message))

class CommandLineInterface:
    @classmethod
    def serve(cls, args):
        parser = ArgumentParser(
            prog=f'{CLI_ENTRY} serve',
            description='Start the mows WebSocket server (replays received events)',
        )
        parser.add_argument('--host', default='0.0.0.0', help='bind address (default: 0.0.0.0)')
        parser.add_argument('--port', type=int, default=8765, help='port (default: 8765)')
        parsed = parser.parse_args(args)

        from .server import run_server
        run_server(parsed.host, parsed.port)

    @classmethod
    def send(cls, args):
        parser = ArgumentParser(
            prog=f'{CLI_ENTRY} send',
            description='Start the mows client (captures and sends events). Press Ctrl+Esc to stop.',
        )
        parser.add_argument('--host', default='localhost', help='server address (default: localhost)')
        parser.add_argument('--port', type=int, default=8765, help='port (default: 8765)')
        parser.add_argument('--suppress', action='store_true', default=False,
                            help='block input events from reaching the client OS (Windows)')
        parsed = parser.parse_args(args)

        from .client import run_client
        run_client(parsed.host, parsed.port, parsed.suppress)

    @classmethod
    def help(cls, args=None):
        help = [
            f"{NAME} v{VERSION}",
            f"Mouse Over WebSocket",
            f"",
            f"Syntax: {CLI_ENTRY} COMMAND [OPTIONS]",
            f"",
            f"Where COMMAND is one of:",
        ]+[f"  {k}" for k in COMMANDS]+[
            f"",
            f"For additional help, use:",
            f"  {CLI_ENTRY} COMMAND -h/--help",
        ]
        help = "\n".join(help)
        print(help)

COMMANDS = [k for k in CommandLineInterface.__dict__ if not k.startswith("_")]

def main():
    if len(sys.argv) <= 1:
        CommandLineInterface.help()
        return

    cmd = sys.argv[1]
    if cmd in COMMANDS:
        getattr(CommandLineInterface, cmd)(sys.argv[2:])
    else:
        CommandLineInterface.help()

if __name__ == "__main__":
    main()
