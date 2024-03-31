# Dune-HD integration for Remote Two

Using [uc-integration-api](https://github.com/aitatoi/integration-python-library)

The driver discovers Apple TV devices on the network and pairs them using AirPlay and companion protocols.
A [media player entity](https://github.com/unfoldedcircle/core-api/blob/main/doc/entities/entity_media_player.md)
is exposed to the Remote Two.

Supported attributes:
- State (on, standby, playing, paused, seeking, buffering, unknown)
- Title
- Artwork
- Media duration
- Media position

Supported commands:
- Turn on & off (device will be put into standby)
- Next / Previous
- Rewind / Fast-forward
- Volume up / down / Mute
- Channel up / down
- Play / pause
- Back
- Directional pad navigation and select
- Digits
- Context menu
- Top menu
- Subtitle
- Audio track

## Usage
### Setup

- Requires Python 3.11
- Install required libraries:  
  (using a [virtual environment](https://docs.python.org/3/library/venv.html) is highly recommended)
```shell
pip3 install -r requirements.txt
```

### Run

```shell
python3 intg-dunehd/driver.py
```

See available [environment variables](https://github.com/unfoldedcircle/integration-python-library#environment-variables)
in the Python integration library to control certain runtime features like listening interface and configuration directory.

The configuration file is loaded & saved from the path specified in the environment variable `UC_CONFIG_HOME`.
Otherwise, the `HOME` path is used or the working directory as fallback.

## Build self-contained binary

After some tests, turns out python stuff on embedded is a nightmare. So we're better off creating a single binary file
that has everything in it.

To do that, we need to compile it on the target architecture as `pyinstaller` does not support cross compilation.

### x86-64 Linux

On x86-64 Linux we need Qemu to emulate the aarch64 target platform:
```bash
sudo apt install qemu binfmt-support qemu-user-static
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
```

Run pyinstaller:
```shell
docker run --rm --name builder \
    --platform=aarch64 \
    --user=$(id -u):$(id -g) \
    -v "$PWD":/workspace \
    docker.io/unfoldedcircle/r2-pyinstaller:3.11.6  \
    bash -c \
      "python -m pip install -r requirements.txt && \
      pyinstaller --clean --onefile --name intg-dunehd intg-dunehd/driver.py"
```

### aarch64 Linux / Mac

On an aarch64 host platform, the build image can be run directly (and much faster):
```shell
docker run --rm --name builder \
    --user=$(id -u):$(id -g) \
    -v "$PWD":/workspace \
    docker.io/unfoldedcircle/r2-pyinstaller:3.11.6  \
    bash -c \
      "python -m pip install -r requirements.txt && \
      pyinstaller --clean --onefile --name intg-dunehd intg-dunehd/driver.py"
```

## Versioning

We use [SemVer](http://semver.org/) for versioning. For the versions available, see the
[tags and releases in this repository](https://github.com/petercv/ucr2-integration-dunehd/releases).

## Changelog

The major changes found in each new release are listed in the [changelog](CHANGELOG.md)
and under the GitHub [releases](https://github.com/unfoldedcircle/integration-appletv/releases).

## License

This project is licensed under the [**Mozilla Public License 2.0**](https://choosealicense.com/licenses/mpl-2.0/).
See the [LICENSE](LICENSE) file for details.
