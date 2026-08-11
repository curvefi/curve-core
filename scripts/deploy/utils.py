import os
import re
import subprocess
from pathlib import Path

from scripts.logging_config import get_logger

logger = get_logger()


def get_latest_commit_hash(file_path):
    try:
        # Run the Git command to get the latest commit hash
        # for the specified file
        result = subprocess.run(
            ["git", "log", "-n", "1", "--pretty=format:%H", "--", file_path],
            capture_output=True,
            text=True,
            check=True,
        )
        # Return the commit hash
        commit_hash = result.stdout.strip()
        if len(commit_hash) == 0:
            logger.warning(f"No commit hash found for {file_path}")
        return commit_hash
    except subprocess.CalledProcessError as e:
        logger.warning(f"Error fetching commit hash: {e}")
        return None


def fetch_filename_from_version(contract_folder: Path, version: str):

    pattern = re.compile(rf".*_v_(\d+).vy")

    for file in contract_folder.iterdir():
        match = pattern.match(os.path.basename(file))
        if match and version in str(file):
            return file

    return None


def fetch_latest_contract(contract_folder: Path) -> Path:
    # Regex pattern to match version numbers in filenames
    contract_name = os.path.basename(contract_folder)
    pattern = re.compile(rf".*_v_(\d+).vy")

    # Filter and sort files by version number
    versions = []
    for file in contract_folder.iterdir():
        match = pattern.match(os.path.basename(file))
        if match:
            version = int(match.group(1))
            versions.append((version, file))

    if not versions:
        raise FileNotFoundError(f"No versions found for contract {contract_name}")

    # Get the file with the highest version number
    latest_version = max(versions, key=lambda x: x[0])
    return latest_version[1]


def get_version_from_filename(filename: Path):
    # Extract the version part (e.g., v_110) from the filename
    version_str = os.path.basename(filename).split("_")[-1].split(".")[0]

    # Ensure the version string is in the correct format
    if len(version_str) == 3:
        major, minor, patch = version_str[0], version_str[1], version_str[2]
        return f"{major}.{minor}.{patch}"
    else:
        raise ValueError("Version string is not in the expected format")


def normalise_version(version) -> str:
    """Drop a leading "v" from a contract version string.

    Upstream repos declare versions as `"v2.1.0"`; this repo records them as `"2.1.0"`,
    which until now meant every vendored contract had to be edited by hand. Accepting both
    forms removes that step - and keeps stored contract_version values consistent with the
    deployments already recorded.

    Strips one "v", and only when a digit follows. `lstrip("vV")` would eat every leading
    v ("vv1.0.0" -> "1.0.0") and mangle anything that merely starts with one ("volatile"
    -> "olatile"), silently turning a malformed version into a plausible-looking one.
    """
    return re.sub(r"^[vV](?=\d)", "", str(version).strip())


def version_a_gt_version_b(a, b):
    def parts(version):
        return list(map(int, normalise_version(version).split(".")))

    return parts(a) > parts(b)


def get_relative_path(contract_file: Path) -> Path:
    contracts_index = contract_file.parts.index("contracts")
    return Path("/").joinpath(*contract_file.parts[contracts_index:])
