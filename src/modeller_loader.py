import os
import sys
import logging
from pathlib import Path

logger = logging.getLogger("modeller_loader")

# Your Modeller installation (Windows)
DEFAULT_MODELLER_DIR = Path(r"E:\Projects\Protein_structure_prediction\Modeller10.7")

def configure_modeller(modeller_dir: Path = DEFAULT_MODELLER_DIR):
    """
    Ensures Modeller is importable by adding modlib + bin to PATH and sys.path.
    Returns True if Modeller successfully imports.
    """
    modeller_dir = Path(modeller_dir)

    modlib = modeller_dir / "modlib"
    bin_dir = modeller_dir / "bin"
    lib_dir = modeller_dir / "lib"

    if not modlib.exists():
        logger.error(f"Modeller modlib directory not found: {modlib}")
        return False

    # 1. Add to sys.path
    if str(modlib) not in sys.path:
        sys.path.insert(0, str(modlib))

    # 2. Add binary directories so modeller dlls load correctly
    for d in [bin_dir, lib_dir]:
        if d.exists() and str(d) not in os.environ["PATH"]:
            os.environ["PATH"] = str(d) + os.pathsep + os.environ["PATH"]

    # 3. License Key
    os.environ["KEY_MODELLER"] = "MODELIRANJE"

    # 4. Test Import
    try:
        import modeller  # noqa
        from modeller.automodel import AutoModel  # noqa
        logger.info("Modeller successfully imported.")
        return True
    except Exception as e:
        logger.error(f"Modeller import failed: {e}")
        return False
