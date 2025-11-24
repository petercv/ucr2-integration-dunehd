set -euo pipefail

cd "$(dirname "$0")/.."

docker run --rm --name builder \
    --user=$(id -u):$(id -g) \
    -v "$PWD":/workspace \
    docker.io/unfoldedcircle/r2-pyinstaller:3.11.6-0.2.0 \
    bash -c \
      "python -m pip install -r requirements.txt && \
       pyinstaller --collect-submodules zeroconf --clean --onedir --name driver -y intg-dunehd/driver.py"

rm -rf dist/release
mkdir -p dist/release
mv dist/driver dist/release/bin
cp driver.json dist/release/
rm -f dist/intg-dunehd.tar.gz
tar -czf dist/intg-dunehd.tar.gz -C dist/release .
