#!/bin/bash
# Wrapper to submit batch jobs with $HOME expanded correctly.
# pyxis (enroot) does not expand shell variables inside #SBATCH directives,
# so container-image and container-mounts must be passed on the command line.

SCRIPT=${1:-batch_pass1.sh}

sbatch \
  --container-image="$HOME/nvidia+pytorch+23.12-py3.sqsh" \
  --container-mounts="$HOME/arthistorical-semantic-data-extraction:/workspace" \
  "$SCRIPT"
