import shlex
import sys

norm_game = r"C:\Games\PS4\Bloodborne"
args = "%ROM%"

formatted_args = args.replace("%ROM%", f'"{norm_game}"')
print("formatted:", formatted_args)
print("split POSIX=True:", shlex.split(formatted_args))
print("split POSIX=False:", shlex.split(formatted_args, posix=False))
