#!/usr/bin/env bash
# Generate a CycloneDX SBOM for the installed Python environment -> sbom.json.
# CI can upload this as a build artifact; `make sbom` / `task sbom` run it locally.
set -euo pipefail

pip install --quiet --disable-pip-version-check cyclonedx-bom >/dev/null

# cyclonedx-py CLI (from the cyclonedx-bom package). Prefer the installed-environment scan.
if cyclonedx-py environment --help >/dev/null 2>&1; then
  cyclonedx-py environment --output-format JSON --output-file sbom.json
else
  cyclonedx-py --format json -o sbom.json -e
fi

echo "wrote sbom.json ($(wc -c < sbom.json) bytes)"
